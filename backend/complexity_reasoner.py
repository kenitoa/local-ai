"""시간 복잡도 추론기 (정적 분석 + LLM 하이브리드).

- backend = "static" : optimizer 의 AST 정적 분석만 사용
- backend = "llm"    : model-server 에 분류만 위임. 실패/타임아웃이면 정적 분석으로 폴백
- backend = "hybrid" : 둘 다 구해서 보수적인(=더 큰) 라벨을 채택. LLM 응답이 깨졌으면 정적 분석 사용

LLM 응답은 다음 한 줄짜리 JSON 만 받아들인다::

    {"class": "O(n log n)", "reason": "<짧은 한국어 근거>"}

라벨은 다음 8개로 정규화한다.

    O(1), O(log n), O(n), O(n log n), O(n^2), O(n^3), O(2^n), unknown
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from typing import Any

import optimizer

log = logging.getLogger(__name__)

VALID_LABELS: tuple[str, ...] = (
    "O(1)", "O(log n)", "O(n)", "O(n log n)",
    "O(n^2)", "O(n^3)", "O(2^n)", "unknown",
)

_LABEL_RANK = {
    "O(1)": 0,
    "O(log n)": 1,
    "O(n)": 2,
    "O(n log n)": 3,
    "O(n^2)": 4,
    "O(n^3)": 5,
    "O(2^n)": 6,
    "unknown": -1,
}

_ALIAS = {
    "o(1)": "O(1)", "o(c)": "O(1)", "o(constant)": "O(1)",
    "o(logn)": "O(log n)", "o(log_n)": "O(log n)", "o(log(n))": "O(log n)",
    "o(n)": "O(n)", "o(linear)": "O(n)",
    "o(nlogn)": "O(n log n)", "o(n*logn)": "O(n log n)",
    "o(nlog(n))": "O(n log n)", "o(n*log(n))": "O(n log n)",
    "o(n^2)": "O(n^2)", "o(n2)": "O(n^2)", "o(n**2)": "O(n^2)",
    "o(quadratic)": "O(n^2)",
    "o(n^3)": "O(n^3)", "o(n3)": "O(n^3)", "o(cubic)": "O(n^3)",
    "o(2^n)": "O(2^n)", "o(2**n)": "O(2^n)", "o(exp)": "O(2^n)",
    "o(exponential)": "O(2^n)",
    "o(n)이하": "O(n)",  # 정적 분석기 표기 보정
}


def _model_server_url() -> str:
    return os.getenv("MODEL_SERVER_URL", "http://model-server:8001").rstrip("/")


def _backend_name() -> str:
    return (os.getenv("OPTIMIZER_COMPLEXITY_BACKEND") or "hybrid").lower().strip()


def _llm_timeout() -> float:
    try:
        return float(os.getenv("COMPLEXITY_LLM_TIMEOUT_SEC", "5"))
    except ValueError:
        return 5.0


def _llm_max_tokens() -> int:
    try:
        return int(os.getenv("COMPLEXITY_LLM_MAX_TOKENS", "64"))
    except ValueError:
        return 64


def _llm_model() -> str | None:
    return (os.getenv("COMPLEXITY_LLM_MODEL") or "").strip() or None


def normalize_label(raw: str | None) -> str:
    if not raw:
        return "unknown"
    s = re.sub(r"\s+", "", str(raw).strip().lower())
    if s in _ALIAS:
        return _ALIAS[s]
    # 이미 정규화된 라벨 (대소문자 무시)
    for label in VALID_LABELS:
        if label.lower().replace(" ", "") == s:
            return label
    return "unknown"


def label_rank(label: str) -> int:
    return _LABEL_RANK.get(label, -1)


def _stronger(a: str, b: str) -> str:
    """두 라벨 중 보수적으로 더 큰(나쁜) 쪽을 반환. unknown 은 가장 약하게 취급."""
    ra, rb = label_rank(a), label_rank(b)
    if ra < 0 and rb < 0:
        return "unknown"
    if ra < 0:
        return b
    if rb < 0:
        return a
    return a if ra >= rb else b


PROMPT_TEMPLATE = """다음 {lang} 코드의 최악(worst-case) 시간 복잡도를 분류하세요.

규칙:
- 라벨은 정확히 다음 중 하나만: O(1), O(log n), O(n), O(n log n), O(n^2), O(n^3), O(2^n), unknown
- 출력은 JSON 한 줄로만. 주석/마크다운 금지.
- 형식: {{"class": "<라벨>", "reason": "<짧은 한국어 근거 한 문장>"}}

[코드]
{code}
"""


def _http_post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any] | None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.info("complexity_reasoner: model-server call failed url=%s err=%s", url, exc)
        return None


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """첫 번째로 등장하는 {...} 덩어리를 찾아 JSON 으로 파싱."""
    if not text:
        return None
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    chunk = text[start:i + 1]
                    try:
                        return json.loads(chunk)
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def _llm_complexity(code: str, language: str) -> dict[str, Any] | None:
    if not code or not code.strip():
        return None
    prompt = PROMPT_TEMPLATE.format(lang=language or "plain", code=code[:6000])
    payload = {
        "prompt": prompt,
        "language": language,
        "task": "complexity",
        "max_tokens": _llm_max_tokens(),
        "temperature": 0.0,
    }
    model = _llm_model()
    if model:
        payload["model"] = model
    res = _http_post_json(
        f"{_model_server_url()}/api/v1/generate",
        payload,
        timeout=_llm_timeout(),
    )
    if not res:
        return None
    text = res.get("text") or res.get("answer") or ""
    obj = _extract_json_object(text) or {}
    label = normalize_label(obj.get("class") or obj.get("complexity"))
    if label == "unknown":
        return None
    return {
        "class": label,
        "source": "llm",
        "reason": str(obj.get("reason") or "")[:240] or None,
        "model": res.get("model") or model,
        "raw_text": text[:240],
    }


def infer_complexity(
    code: str,
    language: str,
    static_result: dict[str, Any] | None = None,
    backend: str | None = None,
) -> dict[str, Any] | None:
    """optimizer.set_complexity_resolver 로 등록되는 진입점.

    반환 dict 는 최소한 ``class`` 와 ``source`` 를 담는다. None 을 돌려주면
    optimizer 는 정적 분석 결과(static_result)를 그대로 사용한다.
    """
    chosen_backend = (backend or _backend_name()).lower()
    if chosen_backend == "static":
        return None  # 정적 결과 그대로 사용

    static = static_result or optimizer._static_complexity(code, language)
    static_label = normalize_label(static.get("class")) if static else "unknown"

    llm = _llm_complexity(code, language)
    if not llm:
        # LLM 실패: 정적 결과 폴백 (단, source 는 fallback 표기)
        if static:
            fallback = dict(static)
            fallback["source"] = f"{static.get('source', 'static')}+llm-fallback"
            fallback["llm_error"] = "no_response"
            fallback.setdefault("backend", chosen_backend)
            return fallback
        return None

    if chosen_backend == "llm":
        merged = dict(llm)
        merged["backend"] = "llm"
        return merged

    # hybrid: 둘 중 더 보수적인(높은 등급) 라벨을 채택
    final_label = _stronger(llm["class"], static_label)
    return {
        "class": final_label,
        "source": "hybrid",
        "backend": "hybrid",
        "reason": llm.get("reason"),
        "static_class": static_label,
        "llm_class": llm["class"],
        "llm_model": llm.get("model"),
        "llm_reason": llm.get("reason"),
        "agreement": static_label == llm["class"],
    }


def install(default_backend: str | None = None) -> None:
    """optimizer 에 resolver 를 등록한다. backend=='static' 이면 등록하지 않음."""
    backend = (default_backend or _backend_name()).lower()
    if backend == "static":
        optimizer.set_complexity_resolver(None)
        log.info("complexity_reasoner installed: backend=static (no LLM)")
        return
    optimizer.set_complexity_resolver(infer_complexity)
    log.info(
        "complexity_reasoner installed: backend=%s timeout=%.1fs max_tokens=%d model=%s",
        backend, _llm_timeout(), _llm_max_tokens(), _llm_model() or "(model-server default)",
    )
