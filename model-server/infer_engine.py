"""local-ai model-server 추론 엔진.

설계 원칙
---------
- **자체 학습형(A안)**: 외부 모델 카탈로그 없음. 콜드스타트 베이스 + 자체 LoRA
  어댑터(또는 풀 fine-tune 체크포인트) 만 로드한다.
- **안전 fallback**: transformers/torch/peft 미설치, 베이스 미다운로드, GPU 없음
  같은 어떤 단일 실패도 서버를 죽이지 않는다. 실패 시 ``available()`` 가
  False 를 반환하고, 호출자는 stub 응답으로 자동 fallback 한다.
- **plan 적용**: ``model_planner`` 가 산출한 ``infer_*`` 값(n_ctx, n_threads,
  n_gpu_layers, max_concurrency)을 그대로 사용한다. 모델 *선택* 은 안 한다.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("model-server.engine")

MODELS_DIR = Path(os.environ.get("MODELS_DIR", "/app/models")).resolve()
LOCAL_DIR = MODELS_DIR / "local"
BASE_DIR = LOCAL_DIR / "base"
RUNS_DIR = LOCAL_DIR / "runs"
STATE_FILE = LOCAL_DIR / "state.json"


def _safe_name(model_id: str) -> str:
    return model_id.replace("/", "__").replace(":", "_")


# ---------------------------------------------------------------------------
# 상태
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_engine_state: dict[str, Any] = {
    "available":      False,
    "reason":         "not loaded",
    "base_path":      None,
    "adapter_path":   None,
    "device":         "cpu",
    "n_ctx":          2048,
    "n_threads":      2,
    "torch_dtype":    None,
    "loaded_at":      None,
}

_model = None       # transformers PreTrainedModel
_tokenizer = None
_torch = None       # 모듈 핸들 (지연 import)
_loaded_signature: tuple[str | None, str | None, str, int, int] | None = None


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------
def _read_cold_start_state() -> dict[str, Any]:
    if not STATE_FILE.is_file():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _resolve_base_path(bootstrap_base_id: str | None) -> Path | None:
    """``models/local/base/<safe(id)>`` 가 존재하면 그 경로 반환."""
    state = _read_cold_start_state()
    cs = state.get("cold_start") or {}

    candidates: list[str] = []
    if bootstrap_base_id:
        candidates.append(bootstrap_base_id)
    if cs.get("base_id"):
        candidates.append(cs["base_id"])

    for cand in candidates:
        p = BASE_DIR / _safe_name(cand)
        if p.is_dir() and (p / "config.json").is_file():
            return p
    return None


def _resolve_checkpoint_path(checkpoint_path: str | None) -> Path | None:
    if not checkpoint_path:
        return None
    candidate = Path(checkpoint_path)
    if not candidate.is_absolute():
        candidate = (MODELS_DIR / checkpoint_path).resolve()
    if candidate.is_dir() and (candidate / "config.json").is_file():
        return candidate
    return None


def _resolve_latest_adapter() -> Path | None:
    """``models/local/runs/`` 아래에서 가장 최근 PEFT 어댑터 디렉터리."""
    if not RUNS_DIR.is_dir():
        return None
    candidates = [
        d for d in RUNS_DIR.iterdir()
        if d.is_dir() and (d / "adapter_config.json").is_file()
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return candidates[0]


def _resolve_adapter_path(adapter_path: str | None) -> Path | None:
    """명시적 adapter 경로가 있으면 우선 사용, 없으면 최신 어댑터 선택."""
    if adapter_path is None:
        return _resolve_latest_adapter()
    if not adapter_path.strip():
        return None

    candidate = Path(adapter_path)
    if not candidate.is_absolute():
        candidate = (MODELS_DIR / candidate).resolve()
    if candidate.is_dir() and (candidate / "adapter_config.json").is_file():
        return candidate
    return None


# ---------------------------------------------------------------------------
# 로드
# ---------------------------------------------------------------------------
def load_from_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
    """현재 plan 으로 베이스 + (있다면) 최신 LoRA 어댑터를 메모리에 로드.

    실패해도 예외를 올리지 않고 _engine_state.reason 에 기록만 한다.
    """
    global _model, _tokenizer, _torch, _loaded_signature
    bootstrap_base_id = runtime.get("bootstrap_base")
    requested_checkpoint = runtime.get("checkpoint_path")
    device_pref = (runtime.get("device") or "cpu").lower()
    n_ctx = int(runtime.get("n_ctx") or 2048)
    n_threads = int(runtime.get("n_threads") or 2)

    # 1) 베이스 경로 확인
    base_path = _resolve_checkpoint_path(requested_checkpoint) or _resolve_base_path(bootstrap_base_id)
    if base_path is None:
        return _set_unavailable(
            f"checkpoint/base not found (requested={requested_checkpoint!r}, base_dir={BASE_DIR}) "
            f"(run scripts/bootstrap_cold_start.py)"
        )

    requested_adapter = runtime.get("adapter_path")
    adapter_path = _resolve_adapter_path(requested_adapter)
    if requested_adapter and adapter_path is None:
        return _set_unavailable(f"requested adapter not found: {requested_adapter}")

    signature = (
        str(base_path),
        str(adapter_path) if adapter_path else None,
        device_pref,
        n_ctx,
        n_threads,
    )
    with _lock:
        if (
            _engine_state.get("available") is True
            and _model is not None
            and _tokenizer is not None
            and _loaded_signature == signature
        ):
            return dict(_engine_state)

    # 2) 무거운 의존성 import (없으면 stub 모드 유지)
    try:
        import torch  # type: ignore
        from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
    except ImportError as exc:
        return _set_unavailable(f"transformers/torch not installed: {exc}")

    _torch = torch

    # 3) device / dtype 결정
    if device_pref in ("cuda", "gpu") and torch.cuda.is_available():
        device = "cuda"
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    elif device_pref == "mps" and getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        device = "mps"
        dtype = torch.float16
    else:
        device = "cpu"
        dtype = torch.float32

    if device == "cpu" and n_threads > 0:
        try:
            torch.set_num_threads(n_threads)
        except Exception as exc:  # noqa: BLE001
            log.warning("torch.set_num_threads failed: %s", exc)

    # 4) 토크나이저/베이스 모델 로드 (오프라인 강제: 추가 다운로드 금지)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            str(base_path), local_files_only=True, trust_remote_code=False,
        )
        model = AutoModelForCausalLM.from_pretrained(
            str(base_path),
            local_files_only=True,
            trust_remote_code=False,
            torch_dtype=dtype,
        )
    except Exception as exc:  # noqa: BLE001
        return _set_unavailable(f"failed to load base from {base_path}: {exc}")

    # 5) (선택) 최신 LoRA 어댑터 적용
    if adapter_path is not None:
        try:
            from peft import PeftModel  # type: ignore
            model = PeftModel.from_pretrained(model, str(adapter_path), is_trainable=False)
            log.info("LoRA adapter loaded from %s", adapter_path)
        except ImportError:
            log.info("peft not installed; skipping adapter %s", adapter_path)
            adapter_path = None
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to load adapter %s: %s", adapter_path, exc)
            adapter_path = None

    try:
        model.to(device)
    except Exception as exc:  # noqa: BLE001
        return _set_unavailable(f"failed to move model to {device}: {exc}")
    model.eval()

    with _lock:
        _model = model
        _tokenizer = tokenizer
        _loaded_signature = signature
        _engine_state.update({
            "available":     True,
            "reason":        "loaded",
            "base_path":     str(base_path),
            "adapter_path":  str(adapter_path) if adapter_path else None,
            "device":        device,
            "n_ctx":         n_ctx,
            "n_threads":     n_threads,
            "torch_dtype":   str(dtype).replace("torch.", ""),
            "loaded_at":     _utcnow_iso(),
        })
    log.info("inference engine ready: %s", _engine_state)
    return state()


def unload() -> None:
    global _model, _tokenizer, _loaded_signature
    with _lock:
        _model = None
        _tokenizer = None
        _loaded_signature = None
        _engine_state.update({"available": False, "reason": "unloaded"})
    if _torch is not None:
        try:
            _torch.cuda.empty_cache()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def state() -> dict[str, Any]:
    with _lock:
        return dict(_engine_state)


def available() -> bool:
    return _engine_state.get("available") is True


# ---------------------------------------------------------------------------
# 추론
# ---------------------------------------------------------------------------
def generate(
    prompt: str,
    *,
    max_new_tokens: int = 512,
    temperature: float = 0.2,
    top_p: float = 0.95,
) -> dict[str, Any]:
    """동기 텍스트 생성. ``available()`` False 일 때 호출하면 RuntimeError."""
    if not available() or _model is None or _tokenizer is None or _torch is None:
        raise RuntimeError(_engine_state.get("reason") or "engine not available")

    n_ctx = int(_engine_state.get("n_ctx") or 2048)
    device = _engine_state.get("device") or "cpu"

    inputs = _tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=max(64, n_ctx - max_new_tokens),
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    do_sample = temperature is not None and temperature > 0
    gen_kwargs = {
        "max_new_tokens": int(max_new_tokens),
        "do_sample":      do_sample,
        "temperature":    float(temperature) if do_sample else 1.0,
        "top_p":          float(top_p) if do_sample else 1.0,
        "pad_token_id":   _tokenizer.eos_token_id,
    }

    with _torch.inference_mode():
        out = _model.generate(**inputs, **gen_kwargs)

    input_len = int(inputs["input_ids"].shape[-1])
    new_tokens = out[0][input_len:]
    text = _tokenizer.decode(new_tokens, skip_special_tokens=True)
    return {
        "text":          text,
        "tokens_input":  input_len,
        "tokens_output": int(new_tokens.shape[-1]),
        "device":        device,
    }


# ---------------------------------------------------------------------------
# 내부
# ---------------------------------------------------------------------------
def _utcnow_iso() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat() + "Z"


def _set_unavailable(reason: str) -> dict[str, Any]:
    global _loaded_signature
    log.info("inference engine unavailable: %s", reason)
    with _lock:
        _loaded_signature = None
        _engine_state.update({
            "available": False,
            "reason":    reason,
            "loaded_at": _utcnow_iso(),
        })
    return state()
