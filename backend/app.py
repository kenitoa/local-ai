"""local-ai backend (Step 5).

Step 5: 로컬 파일 저장 + DB 경로 연결.
업로드/생성된 산출물은 ``data/`` 하위 카테고리별 폴더에 저장하고,
MySQL 의 해당 레코드 ``file_path`` 컬럼에 상대경로를 기록한다.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

import db
import storage

SERVICE_NAME = os.getenv("SERVICE_NAME", "backend")
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
# 기본 라우트
# ---------------------------------------------------------------------------
@app.get("/")
def root():
    return {"service": SERVICE_NAME, "status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "mysql": db.ping(),
        "data_dir": str(storage.DATA_DIR),
    }


@app.on_event("startup")
def _startup():
    storage.ensure_layout()
    log.info("%s service started; DATA_DIR=%s", SERVICE_NAME, storage.DATA_DIR)


# ---------------------------------------------------------------------------
# Step 5: 저장 + DB 연결 엔드포인트
# ---------------------------------------------------------------------------
def _insert_raw_input(
    *,
    input_type: str,
    raw_text: str | None,
    project_id: int | None = None,
    user_tag: str | None = None,
    source_file_path: str | None = None,
) -> int:
    """raw_inputs 행을 만들고 id 반환."""
    return db.execute(
        """
        INSERT INTO raw_inputs (project_id, input_type, raw_text, user_tag, source_file_path)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (project_id, input_type, raw_text, user_tag, source_file_path),
    )


# ---- 1) 이미지 원본 업로드 ----
@app.post("/api/v1/uploads/image")
async def upload_image(
    file: UploadFile = File(...),
    project_id: Optional[int] = Form(None),
    user_tag: Optional[str] = Form(None),
):
    blob = await file.read()
    if not blob:
        raise HTTPException(400, "empty file")

    raw_id = _insert_raw_input(
        input_type="image",
        raw_text=None,
        project_id=project_id,
        user_tag=user_tag,
    )
    saved = storage.save_image_original(
        blob,
        raw_input_id=raw_id,
        original_filename=file.filename,
        mime_type=file.content_type or "image/png",
    )
    image_id = db.execute(
        """
        INSERT INTO image_data (raw_input_id, mime_type, file_path, file_size, sha256)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (raw_id, file.content_type or "image/png", saved.rel_path, saved.size, saved.sha256),
    )
    return {"raw_input_id": raw_id, "image_id": image_id, **saved.as_dict()}


# ---- 2) 이미지 추출 결과(텍스트/코드/스펙/메타) ----
class ImageExtractIn(BaseModel):
    image_id: int
    extracted_text: Optional[str] = None
    extracted_code: Optional[str] = None
    extracted_code_language: Optional[str] = None
    extracted_spec: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    ocr_engine: Optional[str] = None
    ocr_confidence: Optional[float] = None


@app.post("/api/v1/images/{image_id}/extracted")
def store_image_extracted(image_id: int, payload: ImageExtractIn):
    if payload.image_id != image_id:
        raise HTTPException(400, "image_id mismatch")

    row = db.fetch_one("SELECT id, raw_input_id FROM image_data WHERE id=%s", (image_id,))
    if not row:
        raise HTTPException(404, "image_data not found")

    result: dict[str, Any] = {"image_id": image_id}

    if payload.extracted_text:
        s = storage.save_image_extracted_text(payload.extracted_text, image_id=image_id)
        db.execute("UPDATE image_data SET text_file_path=%s WHERE id=%s", (s.rel_path, image_id))
        result["text_file_path"] = s.rel_path

    if payload.extracted_code:
        s = storage.save_image_extracted_code(
            payload.extracted_code,
            image_id=image_id,
            language=payload.extracted_code_language,
        )
        ec_id = db.execute(
            """
            INSERT INTO extracted_code
                (raw_input_id, image_id, language, code_text, ocr_engine, ocr_confidence,
                 file_path, file_size, sha256)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (row["raw_input_id"], image_id, payload.extracted_code_language,
             payload.extracted_code, payload.ocr_engine, payload.ocr_confidence,
             s.rel_path, s.size, s.sha256),
        )
        db.execute("UPDATE image_data SET code_file_path=%s WHERE id=%s", (s.rel_path, image_id))
        result["extracted_code_id"] = ec_id
        result["code_file_path"] = s.rel_path

    if payload.extracted_spec:
        s = storage.save_image_extracted_spec(payload.extracted_spec, image_id=image_id)
        db.execute("UPDATE image_data SET spec_file_path=%s WHERE id=%s", (s.rel_path, image_id))
        result["spec_file_path"] = s.rel_path

    if payload.metadata is not None:
        s = storage.save_image_metadata(payload.metadata, image_id=image_id)
        db.execute("UPDATE image_data SET metadata_file_path=%s WHERE id=%s", (s.rel_path, image_id))
        result["metadata_file_path"] = s.rel_path

    return result


# ---- 3) 모델 답변 저장 ----
class ModelAnswerIn(BaseModel):
    raw_input_id: int
    model_name: str
    answer_text: str
    prompt_text: Optional[str] = None
    model_provider: Optional[str] = None
    requirement_id: Optional[int] = None
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    latency_ms: Optional[int] = None


@app.post("/api/v1/model-answers")
def create_model_answer(payload: ModelAnswerIn):
    answer_id = db.execute(
        """
        INSERT INTO model_answers
            (raw_input_id, requirement_id, model_name, model_provider,
             prompt_text, answer_text, tokens_input, tokens_output, latency_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (payload.raw_input_id, payload.requirement_id, payload.model_name,
         payload.model_provider, payload.prompt_text, payload.answer_text,
         payload.tokens_input, payload.tokens_output, payload.latency_ms),
    )
    s = storage.save_model_answer(
        payload.answer_text,
        answer_id=answer_id,
        model_name=payload.model_name,
    )
    db.execute(
        "UPDATE model_answers SET answer_file_path=%s, file_size=%s, sha256=%s WHERE id=%s",
        (s.rel_path, s.size, s.sha256, answer_id),
    )
    return {"answer_id": answer_id, **s.as_dict()}


# ---- 4) 생성 코드 저장 ----
class GeneratedCodeIn(BaseModel):
    answer_id: int
    code_text: str
    language: Optional[str] = None
    file_name: Optional[str] = None
    is_runnable: bool = False


@app.post("/api/v1/generated-code")
def create_generated_code(payload: GeneratedCodeIn):
    s = storage.save_generated_code(
        payload.code_text,
        answer_id=payload.answer_id,
        language=payload.language,
        file_name=payload.file_name,
    )
    gc_id = db.execute(
        """
        INSERT INTO generated_code
            (answer_id, language, file_name, code_text, is_runnable,
             file_path, file_size, sha256)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (payload.answer_id, payload.language, payload.file_name, payload.code_text,
         int(payload.is_runnable), s.rel_path, s.size, s.sha256),
    )
    return {"generated_code_id": gc_id, **s.as_dict()}


# ---- 5) 최적화 코드 + diff 저장 ----
class OptimizedCodeIn(BaseModel):
    generated_code_id: int
    code_text: str
    language: Optional[str] = None
    optimizer: Optional[str] = None
    improvement_notes: Optional[str] = None


@app.post("/api/v1/optimized-code")
def create_optimized_code(payload: OptimizedCodeIn):
    base = db.fetch_one(
        "SELECT id, code_text, language FROM generated_code WHERE id=%s",
        (payload.generated_code_id,),
    )
    if not base:
        raise HTTPException(404, "generated_code not found")

    language = payload.language or base["language"]
    saved_code = storage.save_optimized_code(
        payload.code_text,
        generated_code_id=payload.generated_code_id,
        language=language,
    )
    diff_text = storage.make_unified_diff(base["code_text"] or "", payload.code_text)
    saved_diff = storage.save_code_diff(
        diff_text,
        generated_code_id=payload.generated_code_id,
    )
    oc_id = db.execute(
        """
        INSERT INTO optimized_code
            (generated_code_id, optimizer, language, code_text, improvement_notes,
             file_path, diff_file_path, file_size, sha256)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (payload.generated_code_id, payload.optimizer, language, payload.code_text,
         payload.improvement_notes, saved_code.rel_path, saved_diff.rel_path,
         saved_code.size, saved_code.sha256),
    )
    return {
        "optimized_code_id": oc_id,
        "code_file_path": saved_code.rel_path,
        "diff_file_path": saved_diff.rel_path,
        "file_size": saved_code.size,
        "sha256": saved_code.sha256,
    }


# ---- 6) 임베딩 저장 ----
class EmbeddingIn(BaseModel):
    target_type: str
    target_id: int
    model_name: str
    vector: list[float]
    content_hash: Optional[str] = None


@app.post("/api/v1/embeddings")
def create_embedding(payload: EmbeddingIn):
    s = storage.save_embedding(
        payload.vector,
        target_type=payload.target_type,
        target_id=payload.target_id,
        model_name=payload.model_name,
    )
    norm = sum(x * x for x in payload.vector) ** 0.5
    emb_id = db.execute(
        """
        INSERT INTO embeddings
            (target_type, target_id, model_name, dim, vector_file_path,
             file_size, sha256, norm, content_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            vector_file_path=VALUES(vector_file_path),
            file_size=VALUES(file_size),
            sha256=VALUES(sha256),
            dim=VALUES(dim),
            norm=VALUES(norm)
        """,
        (payload.target_type, payload.target_id, payload.model_name, len(payload.vector),
         s.rel_path, s.size, s.sha256, norm, payload.content_hash),
    )
    return {"embedding_id": emb_id, **s.as_dict()}


# ---- 7) 디스크 사용량/카테고리 점검 ----
@app.get("/api/v1/storage/info")
def storage_info():
    info: dict[str, Any] = {"data_dir": str(storage.DATA_DIR), "categories": {}}
    for key in [
        "image_original", "image_extracted_text", "image_extracted_code",
        "image_extracted_spec", "image_metadata",
        "code_original", "code_generated", "code_optimized", "code_diff",
        "model_answers", "embeddings", "logs",
    ]:
        p = storage.category_path(key)
        files = list(p.rglob("*")) if p.exists() else []
        info["categories"][key] = {
            "rel_path": p.relative_to(storage.DATA_DIR).as_posix(),
            "exists": p.exists(),
            "file_count": sum(1 for f in files if f.is_file()),
        }
    return info
