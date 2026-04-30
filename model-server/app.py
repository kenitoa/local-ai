"""local-ai model-server (Step 8: LLM 추론 stub)."""
import json
import logging
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel

import infer_engine

SERVICE_NAME = os.getenv("SERVICE_NAME", "model-server")
LOG_DIR = "/app/logs"
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"{SERVICE_NAME}.log")),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(SERVICE_NAME)

app = FastAPI(title=f"local-ai {SERVICE_NAME}")

# ---------------------------------------------------------------------------
# Runtime plan (hardware-aware)
#   backend 의 ``/api/v1/hardware/plan/current`` 를 주기적으로 가져와
#   다음 추론에서 사용한다. 최초 로딩 실패 시 기본값을 사용하므로
#   시스템이 아직 hardware-detector / plan/apply 를 수행하지 않은
#   상황에서도 서비스는 구동된다.
# ---------------------------------------------------------------------------
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000").rstrip("/")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "").strip()

_runtime_lock = threading.Lock()
# 자체 학습형(A안) 기본값.
#   - source 가 'default' 이면 아직 backend plan 을 못 가져온 상태.
#   - "model" 은 자기 학습 가중치의 *체크포인트 라벨* 이지, 외부 모델 ID 가 아니다.
#   - 콜드스타트 가중치는 BOOTSTRAP_BASE_ID (.env) 가 결정.
_runtime: dict = {
    "source":          "default",
    "checkpoint":      os.getenv("LOCAL_CHECKPOINT", "self/cold-start"),
    "device":          os.getenv("MODEL_SERVER_DEVICE", "auto"),
    "n_ctx":           int(os.getenv("LLM_N_CTX", "4096")),
    "n_batch":         int(os.getenv("LLM_N_BATCH", "256")),
    "n_threads":       int(os.getenv("LLM_N_THREADS", "4")),
    "n_gpu_layers":    int(os.getenv("LLM_N_GPU_LAYERS", "0")),
    "max_concurrency": int(os.getenv("LLM_MAX_CONCURRENCY", "1")),
    "bootstrap_base":  os.getenv("BOOTSTRAP_BASE_ID", "Qwen/Qwen2.5-Coder-1.5B"),
    "train":           None,
    "updated_at":      None,
}


def _fetch_plan_from_backend(timeout: float = 2.0) -> dict | None:
    url = f"{BACKEND_URL}/api/v1/hardware/plan/current"
    headers = {"X-API-Key": BACKEND_API_KEY} if BACKEND_API_KEY else {}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
        log.debug("plan fetch failed: %s", exc)
        return None
    return data


def _apply_plan_row(row: dict) -> None:
    """backend `model_plans` row(v2: 자체 학습형) 를 런타임 dict 에 반영."""
    with _runtime_lock:
        _runtime.update({
            "source":          "backend-plan",
            "plan_id":         row.get("id"),
            "fingerprint":     row.get("fingerprint"),
            "device":          row.get("infer_device") or _runtime["device"],
            "n_ctx":           int(row.get("infer_n_ctx") or _runtime["n_ctx"]),
            "n_batch":         int(row.get("infer_n_batch") or _runtime["n_batch"]),
            "n_threads":       int(row.get("infer_n_threads") or _runtime["n_threads"]),
            "n_gpu_layers":    int(row.get("infer_n_gpu_layers") or 0),
            "max_concurrency": int(row.get("infer_max_concurrency") or 1),
            "bootstrap_base":  row.get("bootstrap_base_id") or _runtime["bootstrap_base"],
            "train": {
                "trainable":   bool(row.get("train_trainable")),
                "method":      row.get("train_method"),
                "device":      row.get("train_device"),
                "precision":   row.get("train_precision"),
                "lora_rank":   row.get("train_lora_rank"),
                "per_dev_bs":  row.get("train_per_dev_batch"),
                "grad_accum":  row.get("train_grad_accum_steps"),
                "seq_len":     row.get("train_seq_len"),
                "optimizer":   row.get("train_optimizer"),
            },
            "summary":         row.get("summary"),
            "updated_at":      datetime.utcnow().isoformat() + "Z",
        })


def refresh_plan() -> dict:
    row = _fetch_plan_from_backend()
    if row:
        _apply_plan_row(row)
        log.info("runtime plan applied: device=%s ctx=%s gpu_layers=%s base=%s",
                 _runtime["device"], _runtime["n_ctx"],
                 _runtime["n_gpu_layers"], _runtime["bootstrap_base"])
    # plan 적용 후 추론 엔진을 (재)로드 시도. 실패해도 stub fallback 유지.
    try:
        infer_engine.load_from_runtime(dict(_runtime))
    except Exception as exc:  # noqa: BLE001
        log.warning("infer_engine load failed: %s", exc)
    _resize_inference_semaphore(_runtime.get("max_concurrency") or 1)
    return dict(_runtime)


def current_runtime() -> dict:
    with _runtime_lock:
        return dict(_runtime)


# ---------------------------------------------------------------------------
# 추론 동시성 제어 (plan.infer_max_concurrency)
# ---------------------------------------------------------------------------
_infer_sem_lock = threading.Lock()
_infer_sem = threading.BoundedSemaphore(1)
_infer_sem_size = 1


def _resize_inference_semaphore(new_size: int) -> None:
    global _infer_sem, _infer_sem_size
    new_size = max(1, int(new_size or 1))
    with _infer_sem_lock:
        if new_size == _infer_sem_size:
            return
        _infer_sem = threading.BoundedSemaphore(new_size)
        _infer_sem_size = new_size
        log.info("inference concurrency = %d", new_size)


def _build_prompt(endpoint: str, payload_dict: dict) -> str:
    """학습 데이터 스키마와 1:1 정렬되는 단순 instruction 프롬프트.

    fine-tune 단계에서 동일 포맷의 jsonl 을 생성하므로 베이스 모델 단계에서도
    같은 표현을 그대로 사용한다 (별도 chat-template 의존성 제거).
    """
    lang = payload_dict.get("language") or "plain"
    lib = payload_dict.get("library") or "-"
    req = (payload_dict.get("requirement") or "").strip()
    code = (payload_dict.get("input_code") or "").strip()

    header = f"### Task: {endpoint}\n### Language: {lang}\n### Library: {lib}\n"
    if endpoint == "spec_to_code":
        body = f"### Requirement:\n{req}\n\n### Output (code only):\n"
    elif endpoint == "generate":
        body = f"### Requirement:\n{req}\n\n### Output (code only):\n"
    elif endpoint == "optimize":
        body = (
            f"### Requirement:\n{req}\n\n"
            f"### Input code:\n{code}\n\n"
            f"### Optimized code:\n"
        )
    elif endpoint == "explain":
        body = f"### Code:\n{code}\n\n### Explanation:\n"
    else:
        body = f"### Input:\n{req or code}\n\n### Output:\n"
    return header + body


def _split_code_explanation(text: str) -> tuple[str | None, str | None]:
    """모델 출력이 한 덩어리이므로 fenced code block 이 있으면 분리."""
    if "```" in text:
        # 첫 fenced block 을 코드로, 나머지를 explanation 으로
        parts = text.split("```")
        # parts: [pre, lang+code, post, ...]
        if len(parts) >= 3:
            code_block = parts[1]
            # 첫 줄이 언어 라벨이면 제거
            if "\n" in code_block:
                first, rest = code_block.split("\n", 1)
                code = rest if (first.strip().isalpha() or len(first.strip()) <= 12) else code_block
            else:
                code = code_block
            explanation = (parts[0] + "\n" + "```".join(parts[2:])).strip() or None
            return code.strip(), explanation
    return None, text.strip() or None


def _try_real_generate(
    *,
    endpoint: str,
    payload_dict: dict,
    max_tokens: int,
    temperature: float,
    started: datetime,
    requested_model: str | None,
) -> dict | None:
    """엔진이 준비된 경우 실제 추론 결과 dict, 아니면 None."""
    if not infer_engine.available():
        return None
    prompt = _build_prompt(endpoint, payload_dict)
    try:
        with _infer_sem:
            result = infer_engine.generate(
                prompt,
                max_new_tokens=max_tokens,
                temperature=temperature,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("real generate failed (%s): %s", endpoint, exc)
        return None

    text = result["text"]
    if endpoint in ("explain",):
        code_out, expl = None, text
    else:
        code_out, expl = _split_code_explanation(text)
        if code_out is None:  # fence 없으면 전체를 코드로 간주
            code_out, expl = text, None

    latency_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
    return {
        "endpoint":      endpoint,
        "model":         _effective_model(requested_model),
        "language":      payload_dict.get("language"),
        "library":       payload_dict.get("library"),
        "output_code":   code_out,
        "explanation":   expl,
        "latency_ms":    latency_ms,
        "tokens_input":  result.get("tokens_input"),
        "tokens_output": result.get("tokens_output"),
        "stub":          False,
        "device":        result.get("device"),
    }


@app.get("/")
def root():
    return {"service": SERVICE_NAME, "status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.on_event("startup")
def _startup():
    log.info("%s service started", SERVICE_NAME)
    refresh_plan()


@app.get("/api/v1/runtime")
def api_runtime():
    """현재 적용된 런타임 파라미터를 반환 (hardware plan 반영 여부 확인용)."""
    rt = current_runtime()
    rt["engine"] = infer_engine.state()
    return rt


@app.post("/api/v1/runtime/refresh")
def api_runtime_refresh():
    """backend 에서 최신 plan 을 강제로 다시 당겨온다."""
    return refresh_plan()


# ---------------------------------------------------------------------------
# Step 8: /api/v1/generate - 추론 stub
# 실제 LLM 연동 전까지는 입력을 echo + 간단한 코드 블록을 반환한다.
# ---------------------------------------------------------------------------
class GenerateIn(BaseModel):
    prompt: str
    model: str | None = None
    language: str | None = None
    max_tokens: int | None = 512
    temperature: float | None = 0.2
    task: str | None = None  # infer / optimize


DEFAULT_MODEL = os.getenv("LOCAL_CHECKPOINT", "self/cold-start")


def _effective_model(requested: str | None) -> str:
    """요청에 model 이 없으면 현재 적용된 자체 체크포인트 라벨을 사용."""
    return requested or current_runtime().get("checkpoint") or DEFAULT_MODEL


@app.post("/api/v1/generate")
def generate(payload: GenerateIn):
    model = _effective_model(payload.model)
    lang = payload.language or "plain"
    started = datetime.utcnow()
    task_label = payload.task or "infer"
    text = (
        f"# {model} \u00b7 {task_label} (stub)\n\n"
        f"\uc785\ub825 \uc694\uc57d ({lang}):\n\n"
        f"```\n{(payload.prompt or '')[:1800]}\n```\n\n"
        f"\uc544\uc9c1 \uc2e4\uc81c LLM \uc774 \ub85c\ub4dc\ub418\uc9c0 \uc54a\uc544 stub \uc751\ub2f5\uc744 \ubc18\ud658\ud569\ub2c8\ub2e4.\n"
    )
    latency_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
    return {
        "model": model,
        "task": task_label,
        "text": text,
        "language": lang,
        "latency_ms": latency_ms,
        "tokens_input": len((payload.prompt or "").split()),
        "tokens_output": len(text.split()),
        "stub": True,
    }


# ---------------------------------------------------------------------------
# Step 12: 자체 LLM 추론 서버화 (사진의 4개 API stub)
#   POST /generate       : 일반 코드 생성
#   POST /optimize       : 입력 코드 최적화 (input_code → output_code + explanation)
#   POST /explain        : 코드 설명 (input_code → explanation)
#   POST /spec-to-code   : 요구사항 → 코드 (requirement → output_code)
# 학습 데이터 스키마와 1:1 매핑되도록 입출력을 정렬한다.
# ---------------------------------------------------------------------------
class LlmGenerateIn(BaseModel):
    requirement: str | None = None
    input_code: str | None = None
    language: str | None = None
    library: str | None = None
    model: str | None = None
    max_tokens: int | None = 512
    temperature: float | None = 0.2


class LlmOptimizeIn(BaseModel):
    input_code: str
    requirement: str | None = None
    language: str | None = None
    library: str | None = None
    model: str | None = None


class LlmExplainIn(BaseModel):
    input_code: str
    language: str | None = None
    library: str | None = None
    model: str | None = None


class LlmSpecToCodeIn(BaseModel):
    requirement: str
    language: str | None = None
    library: str | None = None
    model: str | None = None


def _llm_response(
    *,
    endpoint: str,
    model: str | None,
    language: str | None,
    library: str | None,
    output_code: str | None,
    explanation: str | None,
    raw_input: dict,
    started: datetime,
) -> dict:
    latency_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
    return {
        "endpoint": endpoint,
        "model": _effective_model(model),
        "language": language,
        "library": library,
        "output_code": output_code,
        "explanation": explanation,
        "latency_ms": latency_ms,
        "tokens_input": sum(len(str(v).split()) for v in raw_input.values() if v),
        "tokens_output": len((output_code or "").split()) + len((explanation or "").split()),
        "stub": True,
    }


@app.post("/generate")
def llm_generate(payload: LlmGenerateIn):
    started = datetime.utcnow()
    real = _try_real_generate(
        endpoint="generate",
        payload_dict=payload.model_dump(),
        max_tokens=int(payload.max_tokens or 512),
        temperature=float(payload.temperature or 0.2),
        started=started,
        requested_model=payload.model,
    )
    if real is not None:
        return real
    lang = payload.language or "plain"
    code = (
        f"# {DEFAULT_MODEL} stub generate ({lang})\n"
        f"# requirement: {(payload.requirement or '').strip()[:200]}\n"
        f"# library: {payload.library or '-'}\n"
        f"def generated_stub():\n    return None\n"
    )
    explanation = "stub: 실제 LLM 가중치가 아직 학습되지 않아 자리표시자 코드를 반환합니다."
    return _llm_response(
        endpoint="generate",
        model=payload.model,
        language=payload.language,
        library=payload.library,
        output_code=code,
        explanation=explanation,
        raw_input=payload.model_dump(),
        started=started,
    )


@app.post("/optimize")
def llm_optimize(payload: LlmOptimizeIn):
    started = datetime.utcnow()
    real = _try_real_generate(
        endpoint="optimize",
        payload_dict=payload.model_dump(),
        max_tokens=768,
        temperature=0.2,
        started=started,
        requested_model=payload.model,
    )
    if real is not None:
        return real
    optimized = (
        f"# {DEFAULT_MODEL} stub optimize ({payload.language or 'plain'})\n"
        f"# requirement: {(payload.requirement or '').strip()[:200]}\n"
        f"{payload.input_code}\n"
    )
    explanation = (
        "stub: 입력 코드를 그대로 보존하고 헤더 주석만 추가했습니다. "
        "Step 10(코드 최적화 fine-tuning) 이후 실제 최적화 결과로 대체됩니다."
    )
    return _llm_response(
        endpoint="optimize",
        model=payload.model,
        language=payload.language,
        library=payload.library,
        output_code=optimized,
        explanation=explanation,
        raw_input=payload.model_dump(),
        started=started,
    )


@app.post("/explain")
def llm_explain(payload: LlmExplainIn):
    started = datetime.utcnow()
    real = _try_real_generate(
        endpoint="explain",
        payload_dict=payload.model_dump(),
        max_tokens=512,
        temperature=0.3,
        started=started,
        requested_model=payload.model,
    )
    if real is not None:
        return real
    snippet = (payload.input_code or "")[:400]
    explanation = (
        f"stub 설명 ({payload.language or 'plain'}):\n\n"
        f"입력 코드 길이={len(payload.input_code or '')} 글자, "
        f"라이브러리={payload.library or '-'}.\n"
        f"앞부분 미리보기:\n```\n{snippet}\n```\n"
    )
    return _llm_response(
        endpoint="explain",
        model=payload.model,
        language=payload.language,
        library=payload.library,
        output_code=None,
        explanation=explanation,
        raw_input=payload.model_dump(),
        started=started,
    )


@app.post("/spec-to-code")
def llm_spec_to_code(payload: LlmSpecToCodeIn):
    started = datetime.utcnow()
    real = _try_real_generate(
        endpoint="spec_to_code",
        payload_dict=payload.model_dump(),
        max_tokens=768,
        temperature=0.2,
        started=started,
        requested_model=payload.model,
    )
    if real is not None:
        return real
    lang = payload.language or "python"
    code = (
        f"# {DEFAULT_MODEL} stub spec→code ({lang})\n"
        f"# requirement: {payload.requirement.strip()[:300]}\n"
        f"# library: {payload.library or '-'}\n"
        f"def from_requirement():\n"
        f"    \"\"\"요구사항으로부터 생성된 stub 함수.\"\"\"\n"
        f"    return None\n"
    )
    explanation = "stub: requirement → code 변환을 흉내내는 자리표시자 응답입니다."
    return _llm_response(
        endpoint="spec_to_code",
        model=payload.model,
        language=payload.language,
        library=payload.library,
        output_code=code,
        explanation=explanation,
        raw_input=payload.model_dump(),
        started=started,
    )
