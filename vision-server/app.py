"""local-ai vision-server (Step 10: 이미지 타입 분류 + 추출).

흐름:
  이미지 업로드 → image_data/original 저장 → 이미지 타입 분류
    → 타입별 추출 (text / code / spec / metadata)
    → image_data/extracted_* 저장 → MySQL image_data 기록
    → LLM 입력 자료로 연결

지원 타입(8가지):
  - code         : 코드 스크린샷
  - error_log    : 에러 / 스택트레이스
  - algorithm    : 알고리즘 문제(백준/리트코드 등)
  - tech_spec    : 기술 명세서 / 설계 문서
  - api_spec     : API 명세 (REST/GraphQL/OpenAPI)
  - db_design    : DB 설계 (ERD/CREATE TABLE)
  - ui_design    : UI 설계 (와이어프레임/목업)
  - other        : 기타

OCR은 로컬 Tesseract를 기본으로 사용하고, ``VISION_VLM_MODEL_PATH``가 지정되면
로컬 TrOCR/VLM 모델을 우선 사용한다. 모델/바이너리가 없을 때만 메타데이터
placeholder로 폴백한다.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from io import BytesIO
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

SERVICE_NAME = os.getenv("SERVICE_NAME", "vision-server")
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

OCR_ENGINE = os.getenv("OCR_ENGINE", "auto").strip().lower()
OCR_LANGS = os.getenv("OCR_LANGS", "kor+eng").strip() or "eng"
OCR_TESSERACT_CONFIG = os.getenv("OCR_TESSERACT_CONFIG", "--psm 6")
VISION_VLM_MODEL_PATH = os.getenv("VISION_VLM_MODEL_PATH", "").strip()
VISION_VLM_LOCAL_ONLY = os.getenv("VISION_VLM_LOCAL_ONLY", "1").lower() not in ("0", "false", "no")


# ---------------------------------------------------------------------------
# 이미지 타입 정의
# ---------------------------------------------------------------------------
SUPPORTED_TYPES: list[dict[str, str]] = [
    {"key": "code",       "label": "코드 이미지"},
    {"key": "error_log",  "label": "에러 로그 이미지"},
    {"key": "algorithm",  "label": "알고리즘 문제 이미지"},
    {"key": "tech_spec",  "label": "기술 명세서 이미지"},
    {"key": "api_spec",   "label": "API 명세 이미지"},
    {"key": "db_design",  "label": "DB 설계 이미지"},
    {"key": "ui_design",  "label": "UI 설계 이미지"},
    {"key": "other",      "label": "기타 이미지"},
]
SUPPORTED_TYPE_KEYS = {t["key"] for t in SUPPORTED_TYPES}


# 파일명/텍스트에서 타입을 추정하기 위한 키워드(소문자 비교).
_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("error_log",  ("error", "exception", "traceback", "stack",
                    "에러", "오류", "예외", "stacktrace")),
    ("api_spec",   ("api", "endpoint", "openapi", "swagger", "graphql", "rest",
                    "request", "response", "post ", "get ")),
    ("db_design",  ("erd", "schema", "create table", "primary key", "foreign key",
                    "스키마", "데이터베이스", "테이블")),
    ("ui_design",  ("ui", "wireframe", "mockup", "figma", "screen",
                    "화면", "버튼", "레이아웃", "디자인")),
    ("algorithm",  ("algorithm", "leetcode", "백준", "boj", "problem",
                    "complexity", "n^2", "o(n", "문제", "입력", "출력")),
    ("tech_spec",  ("spec", "명세", "requirement", "요구사항", "design doc",
                    "architecture", "설계")),
    ("code",       ("code", "function", "class ", "def ", "import ",
                    "console.log", "print(", "public ", ".py", ".js",
                    ".java", ".go", ".rs", ".cpp", ".ts")),
]


def classify_by_text(text: str | None, *, hint_filename: str | None = None) -> tuple[str, float, str]:
    """텍스트(또는 파일명) 기반 휴리스틱 분류.

    Returns
    -------
    (image_type, confidence, source) - source 는 'hint'/'auto'/'fallback'
    """
    haystack = " ".join(filter(None, [text or "", hint_filename or ""])).lower()
    if not haystack.strip():
        return "other", 0.0, "fallback"

    scores: dict[str, int] = {}
    for tkey, words in _TYPE_KEYWORDS:
        hits = sum(1 for w in words if w in haystack)
        if hits:
            scores[tkey] = hits

    if not scores:
        return "other", 0.1, "fallback"

    best = max(scores, key=lambda k: scores[k])
    total = sum(scores.values()) or 1
    conf = round(min(0.99, 0.4 + 0.15 * scores[best] / total + 0.1 * scores[best]), 4)
    return best, conf, "auto"


# ---------------------------------------------------------------------------
# OCR / VLM engines
# ---------------------------------------------------------------------------
def _open_pil_image(file_path: str | None, image_bytes: bytes | None):
    from PIL import Image  # type: ignore

    if file_path and os.path.exists(file_path):
        return Image.open(file_path).convert("RGB")
    if image_bytes is not None:
        return Image.open(BytesIO(image_bytes)).convert("RGB")
    raise FileNotFoundError("image input not found")


@lru_cache(maxsize=1)
def _load_vlm_ocr_model():
    if not VISION_VLM_MODEL_PATH:
        return None
    try:
        from transformers import AutoProcessor, VisionEncoderDecoderModel  # type: ignore

        processor = AutoProcessor.from_pretrained(
            VISION_VLM_MODEL_PATH,
            local_files_only=VISION_VLM_LOCAL_ONLY,
        )
        model = VisionEncoderDecoderModel.from_pretrained(
            VISION_VLM_MODEL_PATH,
            local_files_only=VISION_VLM_LOCAL_ONLY,
        )
        return processor, model
    except Exception as exc:  # noqa: BLE001
        log.warning("VLM OCR model unavailable path=%s err=%s", VISION_VLM_MODEL_PATH, exc)
        return None


def _run_vlm_ocr(file_path: str | None, image_bytes: bytes | None) -> tuple[str, str, float] | None:
    loaded = _load_vlm_ocr_model()
    if not loaded:
        return None
    processor, model = loaded
    try:
        image = _open_pil_image(file_path, image_bytes)
        pixel_values = processor(images=image, return_tensors="pt").pixel_values
        generated_ids = model.generate(pixel_values, max_new_tokens=384)
        text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
        if text:
            return text, "trocr-vlm", 0.85
    except Exception as exc:  # noqa: BLE001
        log.warning("VLM OCR failed: %s", exc)
    return None


def _run_tesseract_ocr(file_path: str | None, image_bytes: bytes | None) -> tuple[str, str, float] | None:
    try:
        import pytesseract  # type: ignore
    except Exception as exc:  # noqa: BLE001
        log.info("pytesseract unavailable: %s", exc)
        return None

    try:
        image = _open_pil_image(file_path, image_bytes)
        data = pytesseract.image_to_data(
            image,
            lang=OCR_LANGS,
            config=OCR_TESSERACT_CONFIG,
            output_type=pytesseract.Output.DICT,
        )
    except Exception as exc:  # noqa: BLE001
        if "kor" in OCR_LANGS:
            try:
                image = _open_pil_image(file_path, image_bytes)
                data = pytesseract.image_to_data(
                    image,
                    lang="eng",
                    config=OCR_TESSERACT_CONFIG,
                    output_type=pytesseract.Output.DICT,
                )
            except Exception as fallback_exc:  # noqa: BLE001
                log.warning("tesseract OCR failed: %s", fallback_exc)
                return None
        else:
            log.warning("tesseract OCR failed: %s", exc)
            return None

    lines: dict[tuple[int, int, int], list[tuple[int, str]]] = {}
    confidences: list[float] = []
    texts = data.get("text", [])
    confs = data.get("conf", [])
    blocks = data.get("block_num", [])
    paragraphs = data.get("par_num", [])
    line_nums = data.get("line_num", [])
    word_nums = data.get("word_num", [])
    for idx, (text, conf) in enumerate(zip(texts, confs)):
        token = str(text or "").strip()
        if not token:
            continue
        key = (
            int(blocks[idx]) if idx < len(blocks) else 0,
            int(paragraphs[idx]) if idx < len(paragraphs) else 0,
            int(line_nums[idx]) if idx < len(line_nums) else idx,
        )
        word_no = int(word_nums[idx]) if idx < len(word_nums) else idx
        lines.setdefault(key, []).append((word_no, token))
        try:
            score = float(conf)
            if score >= 0:
                confidences.append(score / 100.0)
        except Exception:  # noqa: BLE001
            pass
    reconstructed: list[str] = []
    for key in sorted(lines):
        reconstructed.append(" ".join(token for _, token in sorted(lines[key], key=lambda x: x[0])))
    result = "\n".join(reconstructed).strip()
    if not result:
        return None
    confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.5
    return result, f"tesseract:{OCR_LANGS}", confidence


def _run_stub_ocr(file_path: str | None, image_bytes: bytes | None) -> tuple[str, str, float]:
    parts: list[str] = []
    name: str | None = None
    size = 0
    if file_path:
        name = Path(file_path).name
        try:
            size = os.path.getsize(file_path)
        except OSError:
            size = 0
        parts.append(f"filename={name}")
    if image_bytes is not None:
        size = size or len(image_bytes)
    parts.append(f"bytes={size}")
    text = (
        "[vision-server stub OCR]\n"
        + "\n".join(parts) + "\n"
        "OCR/VLM 엔진을 사용할 수 없어 파일 메타로부터 추정한 placeholder 텍스트입니다.\n"
    )
    return text, "stub-ocr", 0.0


def _run_ocr(file_path: str | None, image_bytes: bytes | None) -> tuple[str, str, float]:
    """Run real local OCR/VLM first, then fall back to metadata placeholder."""
    engines = [OCR_ENGINE] if OCR_ENGINE not in ("", "auto") else ["vlm", "tesseract"]
    for engine in engines:
        if engine in ("vlm", "trocr"):
            result = _run_vlm_ocr(file_path, image_bytes)
        elif engine in ("tesseract", "ocr"):
            result = _run_tesseract_ocr(file_path, image_bytes)
        elif engine == "stub":
            result = _run_stub_ocr(file_path, image_bytes)
        else:
            result = None
        if result and result[0].strip():
            return result
    return _run_stub_ocr(file_path, image_bytes)


# ---------------------------------------------------------------------------
# 타입별 후처리: 텍스트 → (text, code, spec, metadata)
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)


def _split_extraction(image_type: str, text: str, language_hint: str | None) -> dict[str, Any]:
    """이미지 타입에 따라 텍스트를 ``text/code/spec`` 슬롯으로 분배."""
    out: dict[str, Any] = {"text": text, "code": None, "spec": None, "language": language_hint}

    # 1) 명시적 코드 펜스가 있으면 우선 추출
    fences = _FENCE_RE.findall(text or "")
    if fences:
        lang0, code0 = fences[0]
        out["code"] = code0.strip()
        out["language"] = (lang0 or language_hint or None) or None

    # 2) 타입별 기본 매핑
    if image_type == "code":
        if not out["code"]:
            out["code"] = text
        out["spec"] = None
    elif image_type == "error_log":
        # 에러 로그는 spec slot 에 요약, code 는 비워둠
        out["spec"] = "## 에러 로그(원문)\n\n" + (text or "")
    elif image_type in ("algorithm", "tech_spec", "api_spec", "db_design", "ui_design"):
        out["spec"] = "## 추출된 명세\n\n" + (text or "")
    # other: 일반 텍스트만
    return out


# ---------------------------------------------------------------------------
# 라우트
# ---------------------------------------------------------------------------
@app.get("/")
def root():
    return {"service": SERVICE_NAME, "status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/health")
def health():
    return {"status": "ok", "supported_types": [t["key"] for t in SUPPORTED_TYPES]}


@app.on_event("startup")
def _startup():
    log.info("%s service started; types=%s", SERVICE_NAME,
             [t["key"] for t in SUPPORTED_TYPES])


@app.get("/api/v1/image-types")
def image_types():
    """지원하는 이미지 타입 목록 반환 (Web UI 의 select 박스용)."""
    return {"types": SUPPORTED_TYPES}


# --------- 분류 단독 호출 -----------------------------------------------------
class ClassifyIn(BaseModel):
    file_path: str | None = None
    image_base64: str | None = None
    text_hint: str | None = None
    filename: str | None = None


@app.post("/api/v1/classify")
def classify(payload: ClassifyIn):
    img_bytes: bytes | None = None
    if payload.image_base64:
        try:
            img_bytes = base64.b64decode(payload.image_base64, validate=False)
        except Exception:  # noqa: BLE001
            img_bytes = b""

    text_for_classification = payload.text_hint
    if not text_for_classification and (payload.file_path or img_bytes):
        text_for_classification, _engine, _confidence = _run_ocr(payload.file_path, img_bytes)

    name = payload.filename or (Path(payload.file_path).name if payload.file_path else None)
    image_type, confidence, source = classify_by_text(text_for_classification, hint_filename=name)
    return {
        "image_type": image_type,
        "confidence": confidence,
        "source": source,
        "filename": name,
    }


# --------- 추출 (분류 + 타입별 추출) ------------------------------------------
class ExtractIn(BaseModel):
    file_path: str | None = None
    image_base64: str | None = None
    language_hint: str | None = None
    image_type: str | None = None  # 사용자가 미리 지정한 타입 (있으면 그대로 사용)
    filename: str | None = None


@app.post("/api/v1/extract")
def extract(payload: ExtractIn):
    img_bytes: bytes | None = None
    if payload.image_base64:
        try:
            img_bytes = base64.b64decode(payload.image_base64, validate=False)
        except Exception:  # noqa: BLE001
            img_bytes = b""

    if not payload.file_path and img_bytes is None:
        raise HTTPException(400, "file_path 또는 image_base64 중 하나는 필요합니다")

    source = payload.file_path or "inline-base64"
    size = 0
    if payload.file_path:
        try:
            size = os.path.getsize(payload.file_path)
        except OSError:
            size = 0
    elif img_bytes is not None:
        size = len(img_bytes)

    # 1) OCR (현재는 stub)
    raw_text, engine, ocr_confidence = _run_ocr(payload.file_path, img_bytes)

    # 2) 이미지 타입 결정 (명시 > 자동 분류)
    if payload.image_type and payload.image_type in SUPPORTED_TYPE_KEYS:
        image_type = payload.image_type
        type_conf = 1.0
        type_source = "user"
    else:
        name = payload.filename or (Path(payload.file_path).name if payload.file_path else None)
        image_type, type_conf, type_source = classify_by_text(raw_text, hint_filename=name)

    # 3) 타입별 슬롯 분배
    parts = _split_extraction(image_type, raw_text, payload.language_hint)

    # 4) 메타데이터 (이후 backend 가 image_data/metadata/*.json 에 저장)
    metadata = {
        "engine": engine,
        "ocr_confidence": ocr_confidence,
        "image_type": image_type,
        "image_type_confidence": type_conf,
        "image_type_source": type_source,
        "bytes": size,
        "source": source,
        "filename": payload.filename or (Path(payload.file_path).name if payload.file_path else None),
        "language_hint": payload.language_hint,
        "extracted_at": datetime.utcnow().isoformat() + "Z",
    }

    log.info(
        "extract source=%s bytes=%d type=%s conf=%.2f via=%s",
        source, size, image_type, type_conf, type_source,
    )

    return {
        "source": source,
        "bytes": size,
        "engine": engine,
        "confidence": ocr_confidence,
        "image_type": image_type,
        "image_type_confidence": type_conf,
        "image_type_source": type_source,
        "language": parts.get("language"),
        "text": parts.get("text"),
        "code": parts.get("code"),
        "spec": parts.get("spec"),
        "metadata": metadata,
    }


# ===========================================================================
# Step 11: 자체 Vision-Language Model 학습 파이프라인
#
# 사진의 명세를 그대로 반영한다:
#   목표      : 이미지 → 코드 / 텍스트 / 명세 구조 추출
#   학습 단계 :
#     1) 코드 이미지 인식
#     2) 에러 로그 이미지 인식
#     3) 명세서 이미지 인식
#     4) 표 구조 인식
#     5) UI 화면 구조 인식
#   초기 VLM : 이미지 안의 소스코드 영역 탐지 → 코드 텍스트화 → 파일 저장
#              → LLM 입력으로 전달
#
# 본 단계에서는 실제 VLM 학습을 수행하지 않는다(가중치 제공 X). 대신
#   - 학습 데이터(JSON) 스키마와 단계 카탈로그를 정의하고,
#   - 초기 파이프라인(detect → ocr → save) 을 실제 OCR/비전 엔진에 연결한다.
# 로컬 VLM 모델이 설정되지 않은 환경에서는 Tesseract + OpenCV 경로로 동작한다.
# ===========================================================================
VLM_TRAINING_STAGES: list[dict[str, Any]] = [
    {"stage_no": 1, "stage_key": "code_image",
     "label": "코드 이미지 인식", "image_type": "code",
     "is_initial": True,
     "description": "코드 스크린샷에서 영역 탐지 + 텍스트화"},
    {"stage_no": 2, "stage_key": "error_log_image",
     "label": "에러 로그 이미지 인식", "image_type": "error_log",
     "is_initial": False,
     "description": "에러/스택트레이스 이미지에서 텍스트화"},
    {"stage_no": 3, "stage_key": "spec_image",
     "label": "명세서 이미지 인식", "image_type": "tech_spec",
     "is_initial": False,
     "description": "기술/요구사항 명세 이미지의 구조 추출"},
    {"stage_no": 4, "stage_key": "table_structure",
     "label": "표 구조 인식", "image_type": "db_design",
     "is_initial": False,
     "description": "ERD/표 구조의 행/열 인식"},
    {"stage_no": 5, "stage_key": "ui_layout",
     "label": "UI 화면 구조 인식", "image_type": "ui_design",
     "is_initial": False,
     "description": "와이어프레임/목업의 컴포넌트 구조 추출"},
]
VLM_STAGE_KEYS = {s["stage_key"] for s in VLM_TRAINING_STAGES}

# 사진의 학습 데이터 JSON 스키마 (image_type 키는 stage_key 와 동일하게 사용).
VLM_SAMPLE_SCHEMA: dict[str, Any] = {
    "image_path":         "data/image_data/original/sample.png",
    "image_type":         "code_image",
    "expected_text":      "...",
    "expected_code":      "...",
    "expected_structure": {},
}


def _stage_for_image_type(image_type: str | None) -> dict[str, Any] | None:
    if not image_type:
        return None
    for s in VLM_TRAINING_STAGES:
        if s["image_type"] == image_type:
            return s
    return None


@app.get("/api/v1/vlm/stages")
def vlm_stages():
    """학습 단계 카탈로그 + 학습 데이터 JSON 스키마 + 초기 파이프라인 정보."""
    return {
        "stages": VLM_TRAINING_STAGES,
        "sample_schema": VLM_SAMPLE_SCHEMA,
        "initial_pipeline": {
            "name": "code_region_extract",
            "steps": [
                "이미지 안의 소스코드 영역 탐지",
                "코드 텍스트화",
                "파일 저장",
                "LLM 입력으로 전달",
            ],
            "stage_key": "code_image",
        },
    }


# --- 초기 VLM 파이프라인: 코드 영역 탐지 ----------------------------------
def _detect_code_regions(
    file_path: str | None,
    image_bytes: bytes | None,
) -> tuple[list[dict[str, Any]], str]:
    """Detect likely code/text regions with OpenCV, falling back to full frame."""
    width, height = 0, 0
    try:
        from PIL import Image  # type: ignore
        if file_path and os.path.exists(file_path):
            with Image.open(file_path) as im:
                width, height = im.size
        elif image_bytes:
            from io import BytesIO
            with Image.open(BytesIO(image_bytes)) as im:
                width, height = im.size
    except Exception:  # noqa: BLE001
        pass

    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore

        if file_path and os.path.exists(file_path):
            image = cv2.imread(file_path)
        elif image_bytes:
            arr = np.frombuffer(image_bytes, dtype=np.uint8)
            image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        else:
            image = None
        if image is not None:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (18, 4))
            dilated = cv2.dilate(thresh, kernel, iterations=2)
            contours, _hier = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            boxes: list[tuple[int, int, int, int]] = []
            img_h, img_w = gray.shape[:2]
            min_area = max(250, int(img_w * img_h * 0.002))
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                area = w * h
                if area >= min_area and w >= max(24, img_w * 0.08) and h >= 8:
                    boxes.append((x, y, x + w, y + h))
            if boxes:
                x1 = max(0, min(b[0] for b in boxes))
                y1 = max(0, min(b[1] for b in boxes))
                x2 = min(img_w, max(b[2] for b in boxes))
                y2 = min(img_h, max(b[3] for b in boxes))
                return [{
                    "bbox": [x1, y1, x2, y2],
                    "score": round(min(0.95, 0.45 + 0.08 * len(boxes)), 4),
                    "label": "code",
                    "source": "opencv-text-blocks",
                    "block_count": len(boxes),
                }], "opencv-text-blocks"
    except Exception as exc:  # noqa: BLE001
        log.info("opencv region detection fallback: %s", exc)

    region = {
        "bbox": [0, 0, width, height],
        "score": 0.5,
        "label": "code",
        "source": "stub-fullframe",
    }
    return [region], "stub-fullframe"


class VlmCodeRegionIn(BaseModel):
    file_path: str | None = None
    image_base64: str | None = None
    filename: str | None = None
    language_hint: str | None = None


@app.post("/api/v1/vlm/detect-code-region")
def vlm_detect_code_region(payload: VlmCodeRegionIn):
    """초기 VLM 목표:
        ``이미지 안의 소스코드 영역 탐지 → 코드 텍스트화 → (LLM 입력)``

    이 엔드포인트는 **탐지 + OCR** 까지만 수행하고,
    파일 저장과 LLM 호출은 backend 의 ``/api/vlm/code-image-pipeline`` 이
    조립한다(서비스 간 책임 분리).
    """
    img_bytes: bytes | None = None
    if payload.image_base64:
        try:
            img_bytes = base64.b64decode(payload.image_base64, validate=False)
        except Exception:  # noqa: BLE001
            img_bytes = b""

    if not payload.file_path and img_bytes is None:
        raise HTTPException(400, "file_path 또는 image_base64 중 하나는 필요합니다")

    regions, detector = _detect_code_regions(payload.file_path, img_bytes)
    raw_text, ocr_engine, ocr_confidence = _run_ocr(payload.file_path, img_bytes)

    # Stage 1 은 코드 영역만 보므로 spec slot 을 비우고 code slot 으로만 채운다.
    code_text = raw_text
    fences = _FENCE_RE.findall(raw_text or "")
    language = payload.language_hint
    if fences:
        lang0, code0 = fences[0]
        code_text = code0.strip()
        language = (lang0 or language).strip() or language

    return {
        "pipeline": "code_region_extract",
        "stage_key": "code_image",
        "detector": detector,
        "ocr_engine": ocr_engine,
        "ocr_confidence": ocr_confidence,
        "regions": regions,
        "region_count": len(regions),
        "language": language,
        "code": code_text,
        "text": raw_text,
        "filename": payload.filename
            or (Path(payload.file_path).name if payload.file_path else None),
    }

