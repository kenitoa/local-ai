"""local-ai 백엔드 로컬 파일 저장 유틸리티 (Step 5).

DB(MySQL)에는 메타데이터만 저장하고, 실제 파일(이미지/텍스트/코드/임베딩 벡터/
모델 답변)은 ``DATA_DIR`` 하위에 카테고리별로 저장한다.

표준 디렉토리 구조 (컨테이너 내부 ``/app/data`` 기준):

    data/
    ├── image_data/
    │   ├── original/        # 사용자가 업로드한 이미지 원본
    │   ├── extracted_text/  # 이미지에서 OCR/파싱한 일반 텍스트
    │   ├── extracted_code/  # 이미지에서 추출한 코드 스니펫
    │   ├── extracted_spec/  # 이미지에서 추출한 요구사항/스펙 텍스트
    │   └── metadata/        # EXIF / 추출 결과 메타 JSON
    ├── code_data/
    │   ├── original/        # 사용자가 직접 입력/업로드한 원본 코드
    │   ├── generated/       # 모델이 생성한 코드
    │   ├── optimized/       # 최적화/리팩터링된 코드
    │   └── diff/            # generated -> optimized 의 unified diff
    ├── model_answers/       # LLM 답변 원문 (.md)
    ├── embeddings/          # 임베딩 벡터 (.npy 또는 .json)
    └── logs/                # 백엔드 자체 작업 로그

각 ``save_*`` 함수는 ``DATA_DIR`` 기준 **상대 경로**(슬래시 표기) 문자열을
반환한다. 이 문자열을 그대로 DB 컬럼(``file_path`` 등)에 저장하면, 호스트와
컨테이너 어디에서든 동일하게 해석할 수 있다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 경로 정의
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data")).resolve()

# (논리 카테고리 키, 상대 경로) 매핑.
# 외부에서는 카테고리 키만 사용하고, 실제 디스크 경로는 이 모듈만 다룬다.
_CATEGORIES: dict[str, str] = {
    # image_data/*
    "image_original":       "image_data/original",
    "image_extracted_text": "image_data/extracted_text",
    "image_extracted_code": "image_data/extracted_code",
    "image_extracted_spec": "image_data/extracted_spec",
    "image_metadata":       "image_data/metadata",
    # code_data/*
    "code_original":  "code_data/original",
    "code_generated": "code_data/generated",
    "code_optimized": "code_data/optimized",
    "code_diff":      "code_data/diff",
    # 단일 폴더
    "model_answers": "model_answers",
    "embeddings":    "embeddings",
    "logs":          "logs",
    # Step 11: 자체 VLM 학습 파이프라인
    "vlm_dataset":         "vlm_training/dataset",
    "vlm_stage_code":      "vlm_training/dataset/stage_1_code_image",
    "vlm_stage_error":     "vlm_training/dataset/stage_2_error_log_image",
    "vlm_stage_spec":      "vlm_training/dataset/stage_3_spec_image",
    "vlm_stage_table":     "vlm_training/dataset/stage_4_table_structure",
    "vlm_stage_ui":        "vlm_training/dataset/stage_5_ui_layout",
    "vlm_pipeline_output": "vlm_training/pipeline_output",
    # Step 12: 자체 LLM 학습 파이프라인
    "llm_tokenizer":          "llm_training/tokenizer",
    "llm_corpus":             "llm_training/corpus",
    "llm_library":            "llm_training/library",
    "llm_dataset":            "llm_training/dataset",
    "llm_dataset_optimize":   "llm_training/dataset/optimize_code",
    "llm_dataset_spec":       "llm_training/dataset/spec_to_code",
    "llm_dataset_explain":    "llm_training/dataset/explain_code",
    "llm_dataset_instruction":"llm_training/dataset/instruction",
    "llm_dataset_pretrain":   "llm_training/dataset/pretrain",
    "llm_eval":               "llm_training/eval",
    "llm_checkpoints":        "llm_training/checkpoints",
    "llm_runs":               "llm_training/runs",
    "llm_inference":          "llm_training/inference",
    # Step 16: 명세서 기반 SW 생성 엔진
    "spec_engine_input":        "spec_engine/input",
    "spec_engine_intermediate": "spec_engine/intermediate",
    "spec_engine_project":      "spec_engine/project",
}

# Step 11: stage_key → 카테고리 매핑
_VLM_STAGE_CATEGORY: dict[str, str] = {
    "code_image":      "vlm_stage_code",
    "error_log_image": "vlm_stage_error",
    "spec_image":      "vlm_stage_spec",
    "table_structure": "vlm_stage_table",
    "ui_layout":       "vlm_stage_ui",
}

# Step 12: task → 카테고리 매핑 (학습 샘플 JSON 저장 위치)
_LLM_TASK_CATEGORY: dict[str, str] = {
    "optimize_code": "llm_dataset_optimize",
    "spec_to_code":  "llm_dataset_spec",
    "explain_code":  "llm_dataset_explain",
    "instruction":   "llm_dataset_instruction",
    "pretrain":      "llm_dataset_pretrain",
}

LLM_TASK_KEYS: tuple[str, ...] = tuple(_LLM_TASK_CATEGORY.keys())


def ensure_layout() -> None:
    """필요한 모든 하위 디렉토리를 생성 (idempotent)."""
    for rel in _CATEGORIES.values():
        (DATA_DIR / rel).mkdir(parents=True, exist_ok=True)


def category_path(category: str) -> Path:
    """카테고리 키 -> 절대 경로."""
    if category not in _CATEGORIES:
        raise ValueError(f"unknown storage category: {category!r}")
    return DATA_DIR / _CATEGORIES[category]


def to_relative(abs_path: Path) -> str:
    """``DATA_DIR`` 기준 상대 경로를 슬래시 표기로 반환."""
    return abs_path.resolve().relative_to(DATA_DIR).as_posix()


def resolve(rel_path: str) -> Path:
    """DB에 저장된 상대 경로를 절대 경로로 복원 (path traversal 방어 포함)."""
    p = (DATA_DIR / rel_path).resolve()
    if DATA_DIR not in p.parents and p != DATA_DIR:
        raise ValueError(f"path escapes DATA_DIR: {rel_path!r}")
    return p


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------
def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sanitize_stem(stem: str | None, fallback: str = "item") -> str:
    if not stem:
        return fallback
    keep = "-_."
    cleaned = "".join(c if c.isalnum() or c in keep else "_" for c in stem)
    return cleaned.strip("._") or fallback


def _compose_filename(stem: str | None, ext: str, *, owner_id: int | str | None = None) -> str:
    """충돌 방지를 위해 ``<timestamp>_<owner>_<stem>_<short-uuid>.<ext>`` 형태로 구성."""
    parts = [_timestamp()]
    if owner_id is not None:
        parts.append(str(owner_id))
    parts.append(_sanitize_stem(stem))
    parts.append(uuid.uuid4().hex[:8])
    base = "_".join(parts)
    if not ext.startswith("."):
        ext = "." + ext
    return base + ext


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


@dataclass(frozen=True)
class SavedFile:
    """저장 결과. ``rel_path`` 를 DB ``file_path`` 컬럼에 그대로 저장한다."""

    rel_path: str
    abs_path: Path
    size: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.rel_path,
            "file_size": self.size,
            "sha256": self.sha256,
        }


def _write_bytes(category: str, filename: str, data: bytes) -> SavedFile:
    target_dir = category_path(category)
    target_dir.mkdir(parents=True, exist_ok=True)
    abs_path = target_dir / filename
    abs_path.write_bytes(data)
    saved = SavedFile(
        rel_path=to_relative(abs_path),
        abs_path=abs_path,
        size=len(data),
        sha256=_sha256_bytes(data),
    )
    log.info("storage.saved category=%s path=%s size=%d", category, saved.rel_path, saved.size)
    return saved


def _write_text(category: str, filename: str, text: str) -> SavedFile:
    return _write_bytes(category, filename, text.encode("utf-8"))


def _write_json(category: str, filename: str, payload: Any) -> SavedFile:
    blob = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    return _write_bytes(category, filename, blob)


# ---------------------------------------------------------------------------
# 1) 이미지 원본 저장
# ---------------------------------------------------------------------------
def save_image_original(
    data: bytes,
    *,
    raw_input_id: int | None = None,
    original_filename: str | None = None,
    mime_type: str = "image/png",
) -> SavedFile:
    """업로드된 이미지 바이트를 ``image_data/original`` 에 저장."""
    ext = (Path(original_filename).suffix if original_filename else "")
    if not ext:
        ext = "." + (mime_type.split("/")[-1] or "bin")
    stem = Path(original_filename).stem if original_filename else "image"
    fname = _compose_filename(stem, ext, owner_id=raw_input_id)
    return _write_bytes("image_original", fname, data)


# ---------------------------------------------------------------------------
# 2) 이미지에서 추출한 텍스트 / 코드 / 스펙 저장
# ---------------------------------------------------------------------------
def save_image_extracted_text(text: str, *, image_id: int | None = None, stem: str = "text") -> SavedFile:
    return _write_text(
        "image_extracted_text",
        _compose_filename(stem, ".txt", owner_id=image_id),
        text,
    )


def save_image_extracted_code(
    code: str,
    *,
    image_id: int | None = None,
    language: str | None = None,
    stem: str = "code",
) -> SavedFile:
    ext_map = {"python": ".py", "javascript": ".js", "typescript": ".ts",
               "java": ".java", "cpp": ".cpp", "c": ".c", "go": ".go",
               "rust": ".rs", "csharp": ".cs", "kotlin": ".kt"}
    ext = ext_map.get((language or "").lower(), ".txt")
    return _write_text(
        "image_extracted_code",
        _compose_filename(stem, ext, owner_id=image_id),
        code,
    )


def save_image_extracted_spec(spec_text: str, *, image_id: int | None = None) -> SavedFile:
    """이미지에서 추출한 요구사항/스펙(자연어)."""
    return _write_text(
        "image_extracted_spec",
        _compose_filename("spec", ".md", owner_id=image_id),
        spec_text,
    )


def save_image_metadata(meta: dict[str, Any], *, image_id: int | None = None) -> SavedFile:
    return _write_json(
        "image_metadata",
        _compose_filename("meta", ".json", owner_id=image_id),
        meta,
    )


# ---------------------------------------------------------------------------
# 3) 코드 저장 (원본 / 생성 / 최적화 / diff)
# ---------------------------------------------------------------------------
def _code_ext(language: str | None, file_name: str | None) -> str:
    if file_name and Path(file_name).suffix:
        return Path(file_name).suffix
    return {
        "python": ".py", "javascript": ".js", "typescript": ".ts",
        "java": ".java", "cpp": ".cpp", "c": ".c", "go": ".go",
        "rust": ".rs", "csharp": ".cs", "kotlin": ".kt",
    }.get((language or "").lower(), ".txt")


def save_original_code(
    code: str,
    *,
    raw_input_id: int | None = None,
    language: str | None = None,
    file_name: str | None = None,
) -> SavedFile:
    stem = Path(file_name).stem if file_name else "original"
    ext = _code_ext(language, file_name)
    return _write_text("code_original", _compose_filename(stem, ext, owner_id=raw_input_id), code)


def save_generated_code(
    code: str,
    *,
    answer_id: int | None = None,
    language: str | None = None,
    file_name: str | None = None,
) -> SavedFile:
    stem = Path(file_name).stem if file_name else "generated"
    ext = _code_ext(language, file_name)
    return _write_text("code_generated", _compose_filename(stem, ext, owner_id=answer_id), code)


def save_optimized_code(
    code: str,
    *,
    generated_code_id: int | None = None,
    language: str | None = None,
    file_name: str | None = None,
) -> SavedFile:
    stem = Path(file_name).stem if file_name else "optimized"
    ext = _code_ext(language, file_name)
    return _write_text("code_optimized", _compose_filename(stem, ext, owner_id=generated_code_id), code)


def save_code_diff(
    diff_text: str,
    *,
    generated_code_id: int | None = None,
    optimized_code_id: int | None = None,
) -> SavedFile:
    owner = optimized_code_id or generated_code_id
    return _write_text("code_diff", _compose_filename("diff", ".diff", owner_id=owner), diff_text)


def make_unified_diff(before: str, after: str, *, before_label: str = "generated", after_label: str = "optimized") -> str:
    """순수 stdlib 기반 unified diff 생성."""
    import difflib

    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=before_label,
            tofile=after_label,
        )
    )


# ---------------------------------------------------------------------------
# 4) 모델 답변 저장
# ---------------------------------------------------------------------------
def save_model_answer(
    answer_text: str,
    *,
    answer_id: int | None = None,
    model_name: str | None = None,
) -> SavedFile:
    stem = _sanitize_stem(model_name, "answer")
    return _write_text(
        "model_answers",
        _compose_filename(stem, ".md", owner_id=answer_id),
        answer_text,
    )


# ---------------------------------------------------------------------------
# 5) 임베딩 벡터 저장
# ---------------------------------------------------------------------------
def save_embedding(
    vector: Iterable[float],
    *,
    target_type: str,
    target_id: int,
    model_name: str,
    use_numpy: bool = True,
) -> SavedFile:
    """임베딩 벡터를 ``.npy`` (numpy 사용 가능 시) 또는 ``.json`` 으로 저장."""
    stem = f"{_sanitize_stem(target_type)}-{target_id}-{_sanitize_stem(model_name)}"
    if use_numpy:
        try:
            import numpy as np  # type: ignore
        except ImportError:
            use_numpy = False
        else:
            arr = np.asarray(list(vector), dtype="float32")
            fname = _compose_filename(stem, ".npy")
            target_dir = category_path("embeddings")
            target_dir.mkdir(parents=True, exist_ok=True)
            abs_path = target_dir / fname
            np.save(abs_path, arr, allow_pickle=False)
            blob = abs_path.read_bytes()
            return SavedFile(
                rel_path=to_relative(abs_path),
                abs_path=abs_path,
                size=len(blob),
                sha256=_sha256_bytes(blob),
            )
    # numpy 가 없으면 JSON 으로 폴백
    return _write_json(
        "embeddings",
        _compose_filename(stem, ".json"),
        list(vector),
    )


# ---------------------------------------------------------------------------
# 6) Step 11: 자체 VLM 학습 파이프라인 산출물
# ---------------------------------------------------------------------------
def vlm_stage_category(stage_key: str) -> str:
    """학습 단계 키 → 저장 카테고리 키.

    알 수 없는 단계는 공용 ``vlm_dataset`` 카테고리로 폴백한다.
    """
    return _VLM_STAGE_CATEGORY.get(stage_key, "vlm_dataset")


def save_vlm_training_sample(
    sample: dict[str, Any],
    *,
    stage_key: str,
    sample_id: int | None = None,
    stem: str | None = None,
) -> SavedFile:
    """사진의 JSON 스키마를 그대로 디스크에 저장.

    sample 예::

        {
            "image_path": "data/image_data/original/sample.png",
            "image_type": "code_image",
            "expected_text": "...",
            "expected_code": "...",
            "expected_structure": {}
        }
    """
    return _write_json(
        vlm_stage_category(stage_key),
        _compose_filename(stem or stage_key, ".json", owner_id=sample_id),
        sample,
    )


def save_vlm_pipeline_text(
    text: str,
    *,
    pipeline: str = "code_region_extract",
    image_id: int | None = None,
    extension: str = ".txt",
) -> SavedFile:
    """초기 VLM 파이프라인이 추출한 텍스트(코드/로그/명세)를 저장."""
    stem = _sanitize_stem(pipeline, "vlm_output")
    return _write_text(
        "vlm_pipeline_output",
        _compose_filename(stem, extension, owner_id=image_id),
        text,
    )


# ---------------------------------------------------------------------------
# 7) Step 12: 자체 LLM 학습 파이프라인 산출물
# ---------------------------------------------------------------------------
def llm_task_category(task: str) -> str:
    """학습 task → 저장 카테고리. 알 수 없으면 공용 dataset 으로 폴백."""
    return _LLM_TASK_CATEGORY.get(task, "llm_dataset")


def save_llm_training_sample(
    sample: dict[str, Any],
    *,
    task: str,
    sample_id: int | None = None,
    stem: str | None = None,
) -> SavedFile:
    """사진의 JSON 스키마(language/library/task/input_code/requirement/output_code/explanation)
    를 그대로 디스크에 저장한다.
    """
    return _write_json(
        llm_task_category(task),
        _compose_filename(stem or task, ".json", owner_id=sample_id),
        sample,
    )


def save_llm_corpus_file(
    text: str,
    *,
    language: str,
    file_name: str | None = None,
    corpus_id: int | None = None,
) -> SavedFile:
    """언어별 코드 corpus(원문 텍스트)를 ``llm_training/corpus/<language>/`` 에 저장."""
    rel_dir = f"{_CATEGORIES['llm_corpus']}/{_sanitize_stem(language, 'unknown')}"
    target_dir = (DATA_DIR / rel_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(file_name).stem if file_name else "corpus"
    ext = _code_ext(language, file_name)
    abs_path = target_dir / _compose_filename(stem, ext, owner_id=corpus_id)
    blob = text.encode("utf-8")
    abs_path.write_bytes(blob)
    return SavedFile(
        rel_path=to_relative(abs_path),
        abs_path=abs_path,
        size=len(blob),
        sha256=_sha256_bytes(blob),
    )


def save_llm_library_example(
    payload: dict[str, Any],
    *,
    language: str,
    library: str,
    example_id: int | None = None,
) -> SavedFile:
    """라이브러리 문서/예제(JSON) 저장."""
    rel_dir = (
        f"{_CATEGORIES['llm_library']}/"
        f"{_sanitize_stem(language, 'unknown')}/"
        f"{_sanitize_stem(library, 'unknown')}"
    )
    target_dir = (DATA_DIR / rel_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    fname = _compose_filename(library, ".json", owner_id=example_id)
    abs_path = target_dir / fname
    blob = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    abs_path.write_bytes(blob)
    return SavedFile(
        rel_path=to_relative(abs_path),
        abs_path=abs_path,
        size=len(blob),
        sha256=_sha256_bytes(blob),
    )


def save_llm_tokenizer_config(
    config: dict[str, Any],
    *,
    name: str,
) -> SavedFile:
    """토크나이저 설계 JSON 저장."""
    return _write_json(
        "llm_tokenizer",
        _compose_filename(name, ".json"),
        config,
    )


def save_llm_inference_log(
    payload: dict[str, Any],
    *,
    endpoint: str,
    inference_id: int | None = None,
) -> SavedFile:
    """추론 호출 입력/응답을 감사용으로 디스크에 보존."""
    return _write_json(
        "llm_inference",
        _compose_filename(endpoint, ".json", owner_id=inference_id),
        payload,
    )


# ---------------------------------------------------------------------------
# 8) Step 16: 명세서 기반 SW 생성 엔진 산출물
# ---------------------------------------------------------------------------
def save_spec_input_text(
    text: str,
    *,
    run_hint: str | None = None,
    owner_id: int | str | None = None,
) -> SavedFile:
    """입력 명세서 원문(또는 OCR 텍스트)을 보존."""
    return _write_text(
        "spec_engine_input",
        _compose_filename(run_hint or "spec", ".md", owner_id=owner_id),
        text,
    )


def save_spec_intermediate_json(
    payload: dict[str, Any],
    *,
    run_id: int | None = None,
    project_name: str | None = None,
) -> SavedFile:
    """사진의 ``project_name + features + screens + apis + database_tables + business_rules``
    중간 JSON 을 그대로 디스크에 보존."""
    stem = _sanitize_stem(project_name or "intermediate", "intermediate")
    return _write_json(
        "spec_engine_intermediate",
        _compose_filename(stem, ".json", owner_id=run_id),
        payload,
    )


def save_spec_project_file(
    code_text: str,
    *,
    run_id: int,
    project_name: str | None,
    rel_path: str,
) -> SavedFile:
    """엔진이 생성한 프로젝트 파일을 ``spec_engine/project/<run>_<project>/<rel_path>`` 에 저장.

    rel_path 는 프로젝트 루트 기준 상대 경로(예: ``app/main.py``).
    """
    safe_rel = rel_path.replace("\\", "/").lstrip("/")
    if ".." in safe_rel.split("/"):
        raise ValueError(f"invalid rel_path: {rel_path!r}")
    proj_stem = f"run-{run_id}_{_sanitize_stem(project_name or 'project', 'project')}"
    target_dir = category_path("spec_engine_project") / proj_stem / Path(safe_rel).parent
    target_dir.mkdir(parents=True, exist_ok=True)
    abs_path = (category_path("spec_engine_project") / proj_stem / safe_rel).resolve()
    # 위 resolve() 결과가 spec_engine_project 외부로 새지 않도록 마지막 검증
    base = category_path("spec_engine_project").resolve()
    if base not in abs_path.parents and abs_path != base:
        raise ValueError(f"path escapes spec_engine_project: {rel_path!r}")
    blob = code_text.encode("utf-8")
    abs_path.write_bytes(blob)
    return SavedFile(
        rel_path=to_relative(abs_path),
        abs_path=abs_path,
        size=len(blob),
        sha256=_sha256_bytes(blob),
    )


# ---------------------------------------------------------------------------
# 일반 유틸
# ---------------------------------------------------------------------------
def delete(rel_path: str) -> bool:
    """저장된 파일 삭제. 성공 시 True."""
    p = resolve(rel_path)
    if p.is_file():
        p.unlink()
        return True
    if p.is_dir():
        shutil.rmtree(p)
        return True
    return False


# 모듈 import 시점에 디렉토리 보장
ensure_layout()
