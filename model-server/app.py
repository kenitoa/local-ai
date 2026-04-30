"""local-ai model-server (Step 8: LLM 추론 stub)."""
import logging
import os
from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel

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


@app.get("/")
def root():
    return {"service": SERVICE_NAME, "status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.on_event("startup")
def _startup():
    log.info("%s service started", SERVICE_NAME)


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


DEFAULT_MODEL = os.getenv("DEFAULT_LLM_MODEL", "stub-echo")


@app.post("/api/v1/generate")
def generate(payload: GenerateIn):
    model = payload.model or DEFAULT_MODEL
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
        "model": model or DEFAULT_MODEL,
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
