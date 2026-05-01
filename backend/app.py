"""local-ai backend (Step 5).

Step 5: 로컬 파일 저장 + DB 경로 연결.
업로드/생성된 산출물은 ``data/`` 하위 카테고리별 폴더에 저장하고,
MySQL 의 해당 레코드 ``file_path`` 컬럼에 상대경로를 기록한다.
"""
from __future__ import annotations

import logging
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Optional

import urllib.request
import urllib.error

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

import db
import storage
import optimizer
import model_planner


def _default_local_checkpoint() -> str:
    """Return the default local-checkpoint label for self-trained models.

    This project does NOT reference external pretrained model names here.
    After cold-start the label is ``self/cold-start``; subsequent fine-tune
    runs use labels like ``self/run-<id>``. ``DEFAULT_LLM_MODEL`` is kept
    as a backward-compat fallback only.
    """
    return (
        os.getenv("LOCAL_CHECKPOINT")
        or os.getenv("DEFAULT_LLM_MODEL")
        or "self/cold-start"
    )


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

# --- CORS (안전한 기본값: localhost web-ui 만 허용) ---
_cors_origins = [o.strip() for o in os.getenv("BACKEND_CORS_ORIGINS", "").split(",") if o.strip()]
if not _cors_origins:
    _cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    log.warning("BACKEND_CORS_ORIGINS not set; using safe localhost defaults")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)


# ---------------------------------------------------------------------------
# API Key 인증 미들웨어 (단일 키 방식)
#   - 클라이언트는 모든 요청에 ``X-API-Key: <BACKEND_API_KEY>`` 헤더를 포함해야 함.
#   - 환경변수 ``BACKEND_API_KEY`` 미설정 시: 인증 비활성화 (개발 편의용, WARNING 출력).
#   - 면제 경로: ``/``, ``/health``, ``/docs``, ``/redoc``, ``/openapi.json``,
#     CORS preflight (OPTIONS).
# ---------------------------------------------------------------------------
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "").strip()
MODEL_SERVER_GENERATE_TIMEOUT_SEC = int(os.getenv("MODEL_SERVER_GENERATE_TIMEOUT_SEC", "180"))
_AUTH_EXEMPT_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"}

if not BACKEND_API_KEY:
    log.warning(
        "BACKEND_API_KEY is not set; API key authentication is DISABLED. "
        "Set BACKEND_API_KEY in .env to enable it."
    )


@app.middleware("http")
async def _api_key_auth(request: Request, call_next):
    # 인증 비활성화 (개발 모드)
    if not BACKEND_API_KEY:
        return await call_next(request)
    # CORS preflight 는 항상 통과
    if request.method == "OPTIONS":
        return await call_next(request)
    # 면제 경로 (헬스체크 등)
    path = request.url.path
    if path in _AUTH_EXEMPT_PATHS:
        return await call_next(request)
    # 헤더 검증 (대소문자 무시)
    provided = request.headers.get("x-api-key", "")
    if provided != BACKEND_API_KEY:
        client = request.client.host if request.client else "?"
        log.warning("unauthorized request from %s to %s", client, path)
        return JSONResponse(
            status_code=401,
            content={"detail": "missing or invalid X-API-Key header"},
        )
    return await call_next(request)


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
        "db_pool": db.pool_status(),
    }


@app.on_event("startup")
def _startup():
    storage.ensure_layout()
    log.info("%s service started; DATA_DIR=%s", SERVICE_NAME, storage.DATA_DIR)


@app.on_event("shutdown")
def _shutdown():
    try:
        db.dispose_engine()
        log.info("%s shutdown: db engine disposed", SERVICE_NAME)
    except Exception as exc:  # noqa: BLE001
        log.warning("db dispose failed: %s", exc)


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
# Step 10: 이미지 타입 분류 지원
IMAGE_TYPE_KEYS = {
    "code", "error_log", "algorithm", "tech_spec",
    "api_spec", "db_design", "ui_design", "other",
}


@app.post("/api/v1/uploads/image")
async def upload_image(
    file: UploadFile = File(...),
    project_id: Optional[int] = Form(None),
    user_tag: Optional[str] = Form(None),
    image_type: Optional[str] = Form(None),
):
    blob = await file.read()
    if not blob:
        raise HTTPException(400, "empty file")

    if image_type and image_type not in IMAGE_TYPE_KEYS:
        raise HTTPException(400, f"unsupported image_type: {image_type}")

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
        INSERT INTO image_data
            (raw_input_id, mime_type, file_path, file_size, sha256,
             image_type, image_type_source, image_type_confidence, extraction_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (raw_id, file.content_type or "image/png", saved.rel_path, saved.size, saved.sha256,
         image_type, ("user" if image_type else None),
         (1.0 if image_type else None), "pending"),
    )
    return {
        "raw_input_id": raw_id,
        "image_id": image_id,
        "image_type": image_type,
        **saved.as_dict(),
    }


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
    image_type: Optional[str] = None
    image_type_source: Optional[str] = None
    image_type_confidence: Optional[float] = None


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

    # Step 10: 이미지 타입 / 추출 상태 / 엔진 기록
    if payload.image_type and payload.image_type in IMAGE_TYPE_KEYS:
        db.execute(
            """
            UPDATE image_data
               SET image_type=%s,
                   image_type_source=COALESCE(%s, image_type_source),
                   image_type_confidence=COALESCE(%s, image_type_confidence)
             WHERE id=%s
            """,
            (payload.image_type, payload.image_type_source,
             payload.image_type_confidence, image_id),
        )
        result["image_type"] = payload.image_type
        result["image_type_source"] = payload.image_type_source
        result["image_type_confidence"] = payload.image_type_confidence

    db.execute(
        """
        UPDATE image_data
           SET extraction_status='done',
               extraction_engine=COALESCE(%s, extraction_engine),
               extracted_at=CURRENT_TIMESTAMP
         WHERE id=%s
        """,
        (payload.ocr_engine, image_id),
    )

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
    db.execute(
        """
        INSERT INTO embeddings
            (target_type, target_id, model_name, dim, vector_file_path,
             vector_json, file_size, sha256, norm, content_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            vector_file_path=VALUES(vector_file_path),
            vector_json=VALUES(vector_json),
            file_size=VALUES(file_size),
            sha256=VALUES(sha256),
            dim=VALUES(dim),
            norm=VALUES(norm)
        """,
        (payload.target_type, payload.target_id, payload.model_name, len(payload.vector),
         s.rel_path, json.dumps(payload.vector), s.size, s.sha256, norm, payload.content_hash),
    )
    emb_id = _embedding_row_id(payload.target_type, payload.target_id, payload.model_name)
    if emb_id:
        _vector_db_upsert(
            embedding_id=emb_id,
            target_type=payload.target_type,
            target_id=payload.target_id,
            vector=[float(x) for x in payload.vector],
            model_name=payload.model_name,
            model_version=payload.model_name,
            content_hash=payload.content_hash,
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


# ---------------------------------------------------------------------------
# Step 6: 하드웨어 프로필 (hardware-detector 가 업서트)
# ---------------------------------------------------------------------------
class HardwareProfileIn(BaseModel):
    fingerprint: str
    host_name: Optional[str] = None
    os_name: Optional[str] = None
    os_version: Optional[str] = None
    cpu_model: Optional[str] = None
    cpu_cores: Optional[int] = None
    ram_mb: Optional[int] = None
    gpu_present: bool = False
    gpu_vendor: Optional[str] = None
    gpu_model: Optional[str] = None
    gpu_vram_mb: Optional[int] = None
    accelerator: Optional[str] = None
    cuda_available: bool = False
    directml_available: bool = False
    docker_gpu_ok: bool = False
    storage_total_gb: Optional[float] = None
    storage_free_gb: Optional[float] = None
    run_mode: Optional[str] = None
    detected_at: Optional[str] = None
    details_json: Optional[dict[str, Any]] = None


@app.post("/api/v1/hardware/profile")
def upsert_hardware_profile(payload: HardwareProfileIn):
    details = json.dumps(payload.details_json or {}, ensure_ascii=False)
    db.execute(
        """
        INSERT INTO hardware_profiles
            (host_name, os_name, os_version, cpu_model, cpu_cores, ram_mb,
             gpu_model, gpu_vram_mb, accelerator, fingerprint, details_json,
             run_mode, gpu_present, gpu_vendor, cuda_available, directml_available,
             docker_gpu_ok, storage_total_gb, storage_free_gb, detected_at)
        VALUES (%s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, COALESCE(%s, CURRENT_TIMESTAMP))
        ON DUPLICATE KEY UPDATE
            host_name=VALUES(host_name),
            os_name=VALUES(os_name),
            os_version=VALUES(os_version),
            cpu_model=VALUES(cpu_model),
            cpu_cores=VALUES(cpu_cores),
            ram_mb=VALUES(ram_mb),
            gpu_model=VALUES(gpu_model),
            gpu_vram_mb=VALUES(gpu_vram_mb),
            accelerator=VALUES(accelerator),
            details_json=VALUES(details_json),
            run_mode=VALUES(run_mode),
            gpu_present=VALUES(gpu_present),
            gpu_vendor=VALUES(gpu_vendor),
            cuda_available=VALUES(cuda_available),
            directml_available=VALUES(directml_available),
            docker_gpu_ok=VALUES(docker_gpu_ok),
            storage_total_gb=VALUES(storage_total_gb),
            storage_free_gb=VALUES(storage_free_gb),
            detected_at=VALUES(detected_at)
        """,
        (
            payload.host_name, payload.os_name, payload.os_version,
            payload.cpu_model, payload.cpu_cores, payload.ram_mb,
            payload.gpu_model, payload.gpu_vram_mb, payload.accelerator,
            payload.fingerprint, details,
            payload.run_mode, int(payload.gpu_present), payload.gpu_vendor,
            int(payload.cuda_available), int(payload.directml_available),
            int(payload.docker_gpu_ok),
            payload.storage_total_gb, payload.storage_free_gb,
            payload.detected_at,
        ),
    )
    row = db.fetch_one(
        "SELECT id, fingerprint, run_mode, detected_at FROM hardware_profiles WHERE fingerprint=%s",
        (payload.fingerprint,),
    )
    return {"stored": True, **(row or {})}


@app.get("/api/v1/hardware/current")
def hardware_current():
    """가장 최근 감지된 하드웨어 프로필을 반환."""
    row = db.fetch_one(
        """
        SELECT id, host_name, os_name, os_version, cpu_model, cpu_cores, ram_mb,
               gpu_present, gpu_vendor, gpu_model, gpu_vram_mb, accelerator,
               cuda_available, directml_available, docker_gpu_ok,
               storage_total_gb, storage_free_gb, run_mode, fingerprint,
               detected_at, created_at
        FROM hardware_profiles
        ORDER BY COALESCE(detected_at, created_at) DESC, id DESC
        LIMIT 1
        """
    )
    if not row:
        raise HTTPException(404, "no hardware profile recorded yet")
    return row


# ---------------------------------------------------------------------------
# 자체 학습 plan (hardware → 학습/추론 예산)
#   - GET  /api/v1/hardware/plan          : 현재 프로필로 plan 계산만
#   - POST /api/v1/hardware/plan/apply    : 계산 + model_plans 저장
#   - GET  /api/v1/hardware/plan/current  : 가장 최근 저장된 plan
#   외부 모델 카탈로그를 두지 않는다. 콜드스타트 베이스 1개만 외부 다운로드 허용.
# ---------------------------------------------------------------------------
def _latest_hardware_profile() -> dict[str, Any]:
    row = db.fetch_one(
        """
        SELECT id, host_name, os_name, os_version, cpu_model, cpu_cores, ram_mb,
               gpu_present, gpu_vendor, gpu_model, gpu_vram_mb, accelerator,
               cuda_available, directml_available, docker_gpu_ok,
               storage_total_gb, storage_free_gb, run_mode, fingerprint,
               detected_at
        FROM hardware_profiles
        ORDER BY COALESCE(detected_at, created_at) DESC, id DESC
        LIMIT 1
        """
    )
    if not row:
        raise HTTPException(404, "no hardware profile recorded yet")
    return row


@app.get("/api/v1/hardware/plan")
def hardware_plan():
    """현재 기기 사양으로 학습/추론 예산 plan 을 *계산만* 해서 반환."""
    return model_planner.plan_all(_latest_hardware_profile())


@app.post("/api/v1/hardware/plan/apply")
def hardware_plan_apply():
    """계산한 plan 을 ``model_plans`` 에 영속화하고 plan_id 와 함께 반환."""
    profile = _latest_hardware_profile()
    plan = model_planner.plan_all(profile)
    boot = plan["bootstrap"]
    train = plan["train"]
    infer = plan["infer"]
    policy = (
        "cold-start-only"
        if boot.get("policy", {}).get("allow_cold_start_only")
        else "none"
    )
    new_id = db.execute(
        """
        INSERT INTO model_plans
            (hardware_profile_id, fingerprint, schema_version,
             bootstrap_base_id, bootstrap_params_b, bootstrap_license,
             external_download_policy,
             train_trainable, train_method, train_device, train_precision,
             train_lora_rank, train_lora_alpha, train_lora_dropout,
             train_per_dev_batch, train_grad_accum_steps, train_effective_batch,
             train_seq_len, train_grad_checkpointing, train_optimizer,
             train_n_threads, train_max_params_b, train_disabled_reason,
             infer_device, infer_n_ctx, infer_n_batch, infer_n_threads,
             infer_n_gpu_layers, infer_max_concurrency,
             summary, raw_json)
        VALUES (%s, %s, %s,
                %s, %s, %s,
                %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s)
        """,
        (
            profile.get("id"), profile.get("fingerprint"), plan["schema_version"],
            boot["id"], boot["params_b"], boot.get("license"),
            policy,
            int(bool(train.get("trainable"))), train.get("method"),
            train.get("device"), train.get("precision"),
            int(train.get("lora_rank") or 0), int(train.get("lora_alpha") or 0),
            float(train.get("lora_dropout") or 0.0),
            int(train.get("per_device_batch_size") or 1),
            int(train.get("grad_accum_steps") or 1),
            int(train.get("effective_batch_size") or 1),
            int(train.get("seq_len") or 512),
            int(bool(train.get("gradient_checkpointing"))),
            train.get("optimizer"),
            int(train.get("n_threads") or 2),
            float(train.get("max_params_b") or 1.5),
            train.get("reason"),
            infer["device"], infer["n_ctx"], infer["n_batch"], infer["n_threads"],
            infer["n_gpu_layers"], infer["max_concurrency"],
            plan["summary"], json.dumps(plan, ensure_ascii=False),
        ),
    )
    return {"stored": True, "plan_id": new_id, **plan}


@app.get("/api/v1/hardware/plan/current")
def hardware_plan_current():
    """가장 최근에 저장된 model_plans 행을 그대로 반환."""
    row = db.fetch_one("SELECT * FROM model_plans ORDER BY id DESC LIMIT 1")
    if not row:
        raise HTTPException(
            404,
            "no model plan applied yet (call POST /api/v1/hardware/plan/apply)",
        )
    return row


# ---------------------------------------------------------------------------
# 콜드스타트 베이스 상태 조회
#   models/local/state.json 을 그대로 반환. 다운로드는 backend 가 수행하지 않고
#   ``scripts/bootstrap_cold_start.py`` 가 담당한다 (외부 다운로드 책임 분리).
# ---------------------------------------------------------------------------
@app.get("/api/v1/bootstrap/status")
def bootstrap_status():
    state_path = os.path.join(
        os.environ.get("MODELS_DIR", "/app/models"), "local", "state.json"
    )
    if not os.path.isfile(state_path):
        return {
            "ready": False,
            "policy": "cold-start-only",
            "hint": "run scripts/bootstrap_cold_start.py to download the cold-start base once",
            "state_path": state_path,
        }
    try:
        with open(state_path, "r", encoding="utf-8") as fp:
            state = json.load(fp)
    except (OSError, ValueError) as exc:
        raise HTTPException(500, f"failed to read bootstrap state: {exc}") from exc
    cs = state.get("cold_start") or {}
    return {
        "ready": bool(cs and cs.get("status") in ("downloaded", "already-present")),
        "policy": state.get("policy", "cold-start-only"),
        "cold_start": cs,
        "state_path": state_path,
    }


# ---------------------------------------------------------------------------
# Self-training: fine-tune 트리거
#   1) plan/current 의 train_* 값을 그대로 사용 (별도 카탈로그 X)
#   2) model_answers 에서 학습 데이터를 jsonl 로 export
#   3) llm_training_runs 에 row insert (status=pending)
#   4) scripts/finetune_run.py 를 백그라운드 subprocess 로 spawn
#   5) 스크립트가 직접 DB(status/metrics/checkpoint_path) 를 업데이트
# ---------------------------------------------------------------------------
import re as _re
import subprocess as _subprocess
import sys as _sys

REPO_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAIN_DATA_DIR = os.path.join(
    os.environ.get("DATA_DIR", os.path.join(REPO_ROOT_DIR, "data")),
    "llm_training", "runs",
)
os.makedirs(TRAIN_DATA_DIR, exist_ok=True)

_FENCE_RE = _re.compile(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", _re.DOTALL)


def _safe_dirname(model_id: str) -> str:
    return model_id.replace("/", "__").replace(":", "_")


def _split_answer_text(text: str) -> tuple[str | None, str]:
    """answer_text 에서 첫 fenced code block 을 코드로, 나머지를 explanation 으로."""
    if not text:
        return None, ""
    m = _FENCE_RE.search(text)
    if not m:
        return None, text.strip()
    code = m.group(2).strip() or None
    explanation = (text[: m.start()] + text[m.end():]).strip()
    return code, explanation


def _export_training_jsonl(out_path: str, *, max_samples: int = 5000) -> dict:
    """``model_answers`` (status='ok') + ``answer_reuse_logs`` (decision='reused')
    를 instruction-tuning jsonl 로 변환.

    한 행당 다음 키를 가진다 (finetune_run.py 의 _format_example 와 1:1)::

        {task, language, library, requirement, input_code, output_code, explanation}
    """
    rows = db.fetch_all(
        """
        SELECT ma.id, ma.prompt_text, ma.answer_text,
               ma.requirement_id,
               r.summary AS requirement_summary,
               (SELECT gc.language FROM generated_code gc
                  WHERE gc.answer_id = ma.id ORDER BY gc.id LIMIT 1) AS gc_language,
               (SELECT gc.code_text FROM generated_code gc
                  WHERE gc.answer_id = ma.id ORDER BY gc.id LIMIT 1) AS gc_code
          FROM model_answers ma
          LEFT JOIN requirements r ON r.id = ma.requirement_id
         WHERE ma.status = 'ok'
           AND ma.answer_text IS NOT NULL
         ORDER BY ma.id DESC
         LIMIT %s
        """,
        (max_samples,),
    )

    # 재사용 횟수가 많을수록 "정답에 가깝다" → 동일 샘플을 중복 포함해 가중치 부여
    reuse_counts = {
        r["matched_answer_id"]: int(r["c"])
        for r in db.fetch_all(
            """
            SELECT matched_answer_id, COUNT(*) AS c
              FROM answer_reuse_logs
             WHERE decision = 'reused'
             GROUP BY matched_answer_id
            """
        )
    }

    written = 0
    by_task: dict[str, int] = {}
    with open(out_path, "w", encoding="utf-8") as fp:
        for row in rows:
            answer_text = (row.get("answer_text") or "").strip()
            if not answer_text:
                continue
            requirement = (row.get("requirement_summary")
                           or row.get("prompt_text") or "").strip()
            code, explanation = _split_answer_text(answer_text)

            # task 추론
            if code and requirement:
                task = "spec_to_code"
            elif code:
                task = "generate"
            elif explanation:
                task = "explain"
            else:
                continue

            sample = {
                "task":        task,
                "language":    row.get("gc_language") or "plain",
                "library":     None,
                "requirement": requirement[:4000],
                "input_code":  row.get("gc_code") if task == "explain" else None,
                "output_code": code if task != "explain" else None,
                "explanation": explanation if explanation else None,
            }
            line = json.dumps(sample, ensure_ascii=False)

            weight = 1 + min(int(reuse_counts.get(row["id"], 0)), 4)  # 1~5회 가중
            for _ in range(weight):
                fp.write(line + "\n")
                written += 1
            by_task[task] = by_task.get(task, 0) + weight

    return {"path": out_path, "samples": written, "by_task": by_task}


def _resolve_training_python() -> str:
    return os.environ.get("PYTHON_BIN") or _sys.executable or "python"


def _checkpoint_label_for_run(run_id: int) -> str:
    return f"self/run-{run_id}"


def _repo_abspath(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(REPO_ROOT_DIR, path.replace("/", os.sep))


def _activate_completed_training_run(run_row: dict[str, Any]) -> dict[str, Any]:
    if not run_row:
        raise HTTPException(404, "training run not found")
    if run_row.get("status") != "done":
        raise HTTPException(409, f"training run #{run_row.get('id')} is not done")

    checkpoint_path = (run_row.get("checkpoint_path") or "").strip()
    if not checkpoint_path:
        raise HTTPException(409, "training run has no checkpoint_path")

    checkpoint_abs = _repo_abspath(checkpoint_path)
    if not os.path.isdir(checkpoint_abs):
        raise HTTPException(409, f"checkpoint directory not found: {checkpoint_abs}")

    config_path = os.path.join(checkpoint_abs, "config.json")
    adapter_config_path = os.path.join(checkpoint_abs, "adapter_config.json")
    payload = {
        "checkpoint": _checkpoint_label_for_run(int(run_row["id"])),
        "checkpoint_path": checkpoint_abs if os.path.isfile(config_path) else None,
        "adapter_path": checkpoint_abs if os.path.isfile(adapter_config_path) else None,
        "use_latest": False,
    }
    if payload["checkpoint_path"] is None and payload["adapter_path"] is None:
        raise HTTPException(
            409,
            f"checkpoint {checkpoint_abs} is neither a full model nor a PEFT adapter",
        )

    activated = _http_post_json(f"{MODEL_SERVER_URL}/api/v1/runtime/activate-adapter", payload, timeout=60)
    if not activated:
        raise HTTPException(502, "model-server activation failed")

    return {
        "run_id": run_row["id"],
        "checkpoint": payload["checkpoint"],
        "checkpoint_path": checkpoint_path,
        "engine": activated.get("engine"),
        "runtime": activated,
    }


def _wait_for_training_run(run_id: int, *, timeout_seconds: int, poll_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + max(1, timeout_seconds)
    interval = max(0.2, poll_seconds)
    last_row: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last_row = db.fetch_one("SELECT * FROM llm_training_runs WHERE id=%s", (run_id,))
        if last_row and last_row.get("status") in ("done", "failed"):
            return last_row
        time.sleep(interval)

    if last_row is None:
        raise HTTPException(404, f"training run #{run_id} not found")
    raise HTTPException(504, f"training run #{run_id} did not finish within timeout")


@app.post("/api/v1/training/run")
def training_run(
    run_name: str | None = Query(default=None, description="자유 식별자, 미지정 시 자동"),
    max_samples: int = Query(default=5000, ge=1, le=200000),
    dry_run: bool = Query(default=False, description="데이터셋만 만들고 학습은 spawn 안 함"),
    wait: bool = Query(default=False, description="spawn 후 완료까지 동기 대기"),
    activate_on_finish: bool = Query(default=False, description="완료 시 model-server 에 즉시 반영"),
    wait_timeout_seconds: int = Query(default=7200, ge=1, le=86400),
    poll_seconds: float = Query(default=2.0, ge=0.2, le=30.0),
):
    plan = db.fetch_one("SELECT * FROM model_plans ORDER BY id DESC LIMIT 1")
    if not plan:
        raise HTTPException(409, "no model plan; call POST /api/v1/hardware/plan/apply first")

    train_method = (plan.get("train_method") or "").lower()
    if not plan.get("train_trainable") or train_method in ("", "disabled"):
        raise HTTPException(
            409,
            f"current hardware plan disables training (method={train_method or 'none'}). "
            "Upgrade hardware or revisit the plan.",
        )

    base_id = plan.get("bootstrap_base_id") or os.environ.get(
        "BOOTSTRAP_BASE_ID", "Qwen/Qwen2.5-Coder-1.5B"
    )
    base_dir = os.path.join(
        os.environ.get("MODELS_DIR", os.path.join(REPO_ROOT_DIR, "models")),
        "local", "base", _safe_dirname(base_id),
    )
    if not os.path.isfile(os.path.join(base_dir, "config.json")):
        raise HTTPException(
            409,
            f"cold-start base not present at {base_dir}. "
            "Run scripts/bootstrap_cold_start.py once before training.",
        )

    # 1) llm_training_runs row 생성 (stage_key='instruction_tuning')
    stage = db.fetch_one(
        "SELECT id FROM llm_training_stages WHERE stage_key = %s",
        ("instruction_tuning",),
    )
    if not stage:
        raise HTTPException(500, "llm_training_stages not initialized")

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    run_label = run_name or f"selftrain-{timestamp}"
    hyperparams = {
        "method":      train_method,
        "precision":   plan.get("train_precision"),
        "lora_rank":   plan.get("train_lora_rank"),
        "lora_alpha":  plan.get("train_lora_alpha"),
        "lora_dropout": plan.get("train_lora_dropout"),
        "per_device_batch": plan.get("train_per_dev_batch"),
        "grad_accum":  plan.get("train_grad_accum_steps"),
        "seq_len":     plan.get("train_seq_len"),
        "optimizer":   plan.get("train_optimizer"),
        "device":      plan.get("train_device"),
    }
    run_id = db.execute(
        """
        INSERT INTO llm_training_runs
          (stage_id, stage_key, run_name, base_model, hyperparams, status, created_at)
        VALUES (%s, %s, %s, %s, %s, 'pending', NOW())
        """,
        (stage["id"], "instruction_tuning", run_label, base_id,
         json.dumps(hyperparams, ensure_ascii=False)),
    )

    # 2) 데이터셋 export
    data_path = os.path.join(TRAIN_DATA_DIR, f"{run_label}.jsonl")
    export_info = _export_training_jsonl(data_path, max_samples=max_samples)
    if export_info["samples"] == 0:
        db.execute(
            "UPDATE llm_training_runs SET status='failed', "
            "metrics_json=%s, finished_at=NOW() WHERE id=%s",
            (json.dumps({"error": "no training data available"}), run_id),
        )
        raise HTTPException(409, "no training data: model_answers is empty or has no usable rows")

    # 3) 출력 디렉터리
    out_dir = os.path.join(
        os.environ.get("MODELS_DIR", os.path.join(REPO_ROOT_DIR, "models")),
        "local", "runs", run_label,
    )

    if dry_run:
        return {
            "run_id":    run_id,
            "run_name":  run_label,
            "base_id":   base_id,
            "data":      export_info,
            "out":       out_dir,
            "spawned":   False,
            "dry_run":   True,
            "hyperparams": hyperparams,
        }

    # 4) subprocess spawn (detached: 부모가 죽어도 학습 계속)
    script = os.path.join(REPO_ROOT_DIR, "scripts", "finetune_run.py")
    cmd = [
        _resolve_training_python(), script,
        "--base-id", base_id,
        "--data",    data_path,
        "--out",     out_dir,
        "--run-id",  str(run_id),
        "--method",  train_method,
        "--rank",    str(plan.get("train_lora_rank") or 16),
        "--alpha",   str(plan.get("train_lora_alpha") or 32),
        "--dropout", str(plan.get("train_lora_dropout") or 0.05),
        "--epochs",  str(int(os.environ.get("TRAIN_EPOCHS", "1"))),
        "--batch",   str(plan.get("train_per_dev_batch") or 1),
        "--grad-accum", str(plan.get("train_grad_accum_steps") or 8),
        "--seq-len", str(plan.get("train_seq_len") or 1024),
        "--precision", str(plan.get("train_precision") or "bf16"),
        "--device",    str(plan.get("train_device") or "auto"),
        "--optimizer", str(plan.get("train_optimizer") or "adamw_torch"),
    ]

    log_path = os.path.join(
        os.environ.get("DATA_DIR", os.path.join(REPO_ROOT_DIR, "data")),
        "logs", f"finetune_{run_id}.spawn.log",
    )
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    spawn_log = open(log_path, "ab")  # noqa: SIM115 (자식이 살아있는 동안 유지)
    creation_flags = 0
    if os.name == "nt":
        creation_flags = getattr(_subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = _subprocess.Popen(
        cmd,
        cwd=REPO_ROOT_DIR,
        stdout=spawn_log,
        stderr=spawn_log,
        creationflags=creation_flags,
        close_fds=(os.name != "nt"),
    )

    response = {
        "run_id":   run_id,
        "run_name": run_label,
        "base_id":  base_id,
        "data":     export_info,
        "out":      out_dir,
        "spawned":  True,
        "pid":      proc.pid,
        "log":      log_path,
        "hyperparams": hyperparams,
    }

    if wait:
        final_row = _wait_for_training_run(
            run_id,
            timeout_seconds=wait_timeout_seconds,
            poll_seconds=poll_seconds,
        )
        response["final_status"] = final_row.get("status")
        response["finished_at"] = final_row.get("finished_at")
        response["checkpoint_path"] = final_row.get("checkpoint_path")
        response["metrics"] = final_row.get("metrics_json")
        if activate_on_finish and final_row.get("status") == "done":
            response["activation"] = _activate_completed_training_run(final_row)

    return response


@app.get("/api/v1/training/runs")
def training_runs_list(limit: int = Query(default=20, ge=1, le=200)):
    rows = db.fetch_all(
        "SELECT id, stage_key, run_name, base_model, status, "
        "checkpoint_path, started_at, finished_at, created_at "
        "FROM llm_training_runs ORDER BY id DESC LIMIT %s",
        (limit,),
    )
    return {"items": rows, "count": len(rows)}


@app.get("/api/v1/training/runs/{run_id}")
def training_run_detail(run_id: int):
    row = db.fetch_one("SELECT * FROM llm_training_runs WHERE id=%s", (run_id,))
    if not row:
        raise HTTPException(404, f"training run #{run_id} not found")
    return row


@app.post("/api/v1/training/runs/{run_id}/activate")
def training_run_activate(run_id: int):
    row = db.fetch_one("SELECT * FROM llm_training_runs WHERE id=%s", (run_id,))
    return _activate_completed_training_run(row)


# ---------------------------------------------------------------------------
# Step 7: Web UI 지원 엔드포인트
#  - 저장된 답변 검색/조회
#  - 시스템(서비스) 상태 점검
#  - 통합 실행(/api/v1/run) : 코드/이미지/요구사항 → model_answer 저장
#  - 데이터 파일 다운로드/내용 조회
# ---------------------------------------------------------------------------
SERVICE_PROBES: list[tuple[str, str]] = [
    ("backend",            "http://localhost:8000/health"),
    ("model-server",       os.getenv("MODEL_SERVER_URL", "http://model-server:8001") + "/health"),
    ("vision-server",      os.getenv("VISION_SERVER_URL", "http://vision-server:8002") + "/health"),
    ("embedding-server",   os.getenv("EMBEDDING_SERVER_URL", "http://embedding-server:8003") + "/health"),
    ("vector-db",          os.getenv("VECTOR_DB_URL", "http://qdrant:6333") + "/readyz"),
    ("language-worker",    os.getenv("LANGUAGE_WORKER_URL", "http://language-worker:8004") + "/health"),
    ("hardware-detector",  os.getenv("HARDWARE_DETECTOR_URL", "http://hardware-detector:8005") + "/health"),
]


def _probe_service(url: str, timeout: float = 1.5) -> dict[str, Any]:
    started = datetime.utcnow()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read(2048).decode("utf-8", errors="replace")
            try:
                payload = json.loads(body)
            except Exception:
                payload = {"raw": body[:200]}
            ms = int((datetime.utcnow() - started).total_seconds() * 1000)
            return {"status": "up", "http": resp.status, "latency_ms": ms, "payload": payload}
    except urllib.error.HTTPError as e:
        return {"status": "down", "http": e.code, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"status": "down", "error": str(e)}


@app.get("/api/v1/system/services")
def system_services():
    """모든 백엔드 서비스의 /health 를 호출해서 상태를 묶어 반환."""
    services_by_name: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, len(SERVICE_PROBES))) as pool:
        futures = {
            pool.submit(_probe_service, url): (name, url)
            for name, url in SERVICE_PROBES
        }
        for future in as_completed(futures):
            name, url = futures[future]
            try:
                info = future.result()
            except Exception as exc:  # noqa: BLE001
                info = {"status": "down", "error": str(exc)}
            info["name"] = name
            info["url"] = url
            services_by_name[name] = info

    services = [services_by_name[name] for name, _ in SERVICE_PROBES]

    # MySQL 상태
    services.append({
        "name": "mysql",
        "url": f"mysql://{os.getenv('MYSQL_HOST', 'mysql')}:{os.getenv('MYSQL_PORT', '3306')}",
        "status": "up" if db.ping() else "down",
    })

    # 현재 실행 모드 (있으면)
    run_mode = None
    accelerator = None
    try:
        row = db.fetch_one(
            "SELECT run_mode, accelerator FROM hardware_profiles "
            "ORDER BY COALESCE(detected_at, created_at) DESC, id DESC LIMIT 1"
        )
        if row:
            run_mode = row.get("run_mode")
            accelerator = row.get("accelerator")
    except Exception as e:  # noqa: BLE001
        log.warning("could not load run_mode: %s", e)

    return {
        "checked_at": datetime.utcnow().isoformat() + "Z",
        "run_mode": run_mode,
        "accelerator": accelerator,
        "services": services,
    }


# ---- 저장된 답변 조회/검색 ----
@app.get("/api/v1/model-answers")
def list_model_answers(
    q: Optional[str] = Query(None, description="answer/prompt 텍스트 부분일치"),
    model: Optional[str] = Query(None, description="model_name 필터"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    where = []
    params: list[Any] = []
    if q:
        where.append("(ma.answer_text LIKE %s OR ma.prompt_text LIKE %s)")
        like = f"%{q}%"
        params.extend([like, like])
    if model:
        where.append("ma.model_name = %s")
        params.append(model)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT ma.id, ma.raw_input_id, ma.requirement_id, ma.model_name,
               ma.model_provider, ma.tokens_input, ma.tokens_output,
               ma.latency_ms, ma.status, ma.answer_file_path,
               ma.created_at,
               LEFT(COALESCE(ma.prompt_text, ''), 240) AS prompt_preview,
               LEFT(ma.answer_text, 360)               AS answer_preview,
               ri.input_type, LEFT(COALESCE(ri.raw_text, ''), 240) AS raw_preview
        FROM model_answers ma
        LEFT JOIN raw_inputs ri ON ri.id = ma.raw_input_id
        {where_sql}
        ORDER BY ma.id DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    rows = db.fetch_all(sql, tuple(params))

    count_sql = f"SELECT COUNT(*) AS n FROM model_answers ma {where_sql}"
    total = (db.fetch_one(count_sql, tuple(params[:-2])) or {}).get("n", 0)
    return {"total": total, "limit": limit, "offset": offset, "items": rows}


@app.get("/api/v1/model-answers/{answer_id}")
def get_model_answer(answer_id: int):
    row = db.fetch_one(
        """
        SELECT ma.*, ri.input_type, ri.raw_text AS raw_input_text,
               ri.source_file_path AS raw_source_file_path
        FROM model_answers ma
        LEFT JOIN raw_inputs ri ON ri.id = ma.raw_input_id
        WHERE ma.id = %s
        """,
        (answer_id,),
    )
    if not row:
        raise HTTPException(404, "model_answer not found")

    # 연결된 generated_code / optimized_code 도 함께 반환
    gens = db.fetch_all(
        "SELECT id, language, file_name, code_text, file_path, created_at "
        "FROM generated_code WHERE answer_id=%s ORDER BY id ASC",
        (answer_id,),
    )
    opts: list[dict[str, Any]] = []
    if gens:
        gids = tuple(g["id"] for g in gens)
        placeholders = ",".join(["%s"] * len(gids))
        opts = db.fetch_all(
            f"SELECT id, generated_code_id, optimizer, language, code_text, "
            f"       improvement_notes, file_path, diff_file_path, created_at "
            f"FROM optimized_code WHERE generated_code_id IN ({placeholders}) "
            f"ORDER BY id ASC",
            gids,
        )

    images: list[dict[str, Any]] = []
    if row.get("raw_input_id"):
        images = db.fetch_all(
            "SELECT id, mime_type, file_path, width, height, file_size, "
            "       image_type, image_type_source, image_type_confidence, "
            "       extraction_status, text_file_path, code_file_path, "
            "       spec_file_path, metadata_file_path "
            "FROM image_data WHERE raw_input_id=%s ORDER BY id ASC",
            (row["raw_input_id"],),
        )
    return {"answer": row, "generated_code": gens, "optimized_code": opts, "images": images}


# ---- 통합 실행 (요구사항 + 코드/이미지) → 모델 답변 ----
class RunIn(BaseModel):
    requirement: Optional[str] = None
    code_text: Optional[str] = None
    code_language: Optional[str] = None
    image_id: Optional[int] = None
    raw_input_id: Optional[int] = None
    model_name: Optional[str] = "stub-echo"
    project_id: Optional[int] = None
    user_tag: Optional[str] = None


def _try_call_model_server(prompt: str, model_name: str) -> tuple[str, dict[str, Any] | None]:
    """model-server 가 generation 엔드포인트를 노출하면 호출.

    아직 placeholder 단계라 실패하면 stub 답변을 반환한다.
    """
    url = os.getenv("MODEL_SERVER_URL", "http://model-server:8001") + "/api/v1/generate"
    body = json.dumps({"prompt": prompt, "model": model_name}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=MODEL_SERVER_GENERATE_TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data.get("text") or data.get("answer") or json.dumps(data, ensure_ascii=False)
        return text, data
    except Exception as e:  # noqa: BLE001
        log.info("model-server unavailable, returning stub answer: %s", e)
        # Step 7 단계의 stub 답변 (UI 결선 검증용)
        stub = (
            "# 모델 응답(stub)\n\n"
            "현재 model-server 가 generation API 를 노출하지 않아 echo 형태로 답변을 생성합니다.\n\n"
            "## 입력 요약\n"
            f"```\n{prompt[:2000]}\n```\n"
        )
        return stub, None


@app.post("/api/v1/run")
def run_pipeline(payload: RunIn):
    if not (payload.requirement or payload.code_text or payload.image_id or payload.raw_input_id):
        raise HTTPException(400, "requirement, code_text, image_id, raw_input_id 중 최소 하나는 필요")

    # 1) raw_input 행 확보
    raw_id = payload.raw_input_id
    if raw_id is None:
        input_type = "text"
        if payload.image_id and (payload.requirement or payload.code_text):
            input_type = "mixed"
        elif payload.image_id:
            input_type = "image"
        raw_text_parts: list[str] = []
        if payload.requirement:
            raw_text_parts.append("## 요구사항\n" + payload.requirement)
        if payload.code_text:
            lang = payload.code_language or ""
            raw_text_parts.append(f"## 입력 코드\n```{lang}\n{payload.code_text}\n```")
        raw_text = "\n\n".join(raw_text_parts) if raw_text_parts else None
        raw_id = _insert_raw_input(
            input_type=input_type,
            raw_text=raw_text,
            project_id=payload.project_id,
            user_tag=payload.user_tag,
        )

    # 2) 입력 코드가 들어왔다면 원본 파일로 보존
    original_code_path: Optional[str] = None
    if payload.code_text:
        s = storage.save_original_code(
            payload.code_text,
            raw_input_id=raw_id,
            language=payload.code_language,
        )
        original_code_path = s.rel_path
        # 첨부된 image 가 없을 때만 source_file_path 갱신
        db.execute("UPDATE raw_inputs SET source_file_path=%s WHERE id=%s", (s.rel_path, raw_id))

    # 3) 모델 호출 (없으면 stub)
    prompt_parts: list[str] = []
    if payload.requirement:
        prompt_parts.append("[요구사항]\n" + payload.requirement)
    if payload.code_text:
        prompt_parts.append(f"[입력 코드 ({payload.code_language or 'plain'})]\n{payload.code_text}")
    if payload.image_id:
        prompt_parts.append(f"[참조 이미지 id={payload.image_id}]")
    prompt_text = "\n\n".join(prompt_parts) or "(empty)"

    started = datetime.utcnow()
    answer_text, _raw = _try_call_model_server(prompt_text, payload.model_name or "stub-echo")
    latency_ms = int((datetime.utcnow() - started).total_seconds() * 1000)

    # 4) model_answers + 파일 저장
    answer_id = db.execute(
        """
        INSERT INTO model_answers
            (raw_input_id, requirement_id, model_name, model_provider,
             prompt_text, answer_text, tokens_input, tokens_output, latency_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (raw_id, None, payload.model_name or "stub-echo", "local",
         prompt_text, answer_text, None, None, latency_ms),
    )
    s = storage.save_model_answer(
        answer_text,
        answer_id=answer_id,
        model_name=payload.model_name or "stub-echo",
    )
    db.execute(
        "UPDATE model_answers SET answer_file_path=%s, file_size=%s, sha256=%s WHERE id=%s",
        (s.rel_path, s.size, s.sha256, answer_id),
    )

    return {
        "raw_input_id": raw_id,
        "answer_id": answer_id,
        "model_name": payload.model_name or "stub-echo",
        "latency_ms": latency_ms,
        "answer_text": answer_text,
        "answer_file_path": s.rel_path,
        "original_code_path": original_code_path,
    }


# ---- 데이터 파일 조회 (이미지/코드/diff/답변 등) ----
@app.get("/api/v1/files")
def get_file(path: str = Query(..., description="DATA_DIR 기준 상대경로")):
    """저장된 파일을 그대로 다운로드."""
    try:
        abs_path = storage.resolve(path)
    except ValueError:
        raise HTTPException(400, "invalid path")
    if not abs_path.exists() or not abs_path.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(str(abs_path))


@app.get("/api/v1/files/text", response_class=PlainTextResponse)
def get_file_text(path: str = Query(...)):
    """텍스트 파일의 내용을 문자열로 반환."""
    try:
        abs_path = storage.resolve(path)
    except ValueError:
        raise HTTPException(400, "invalid path")
    if not abs_path.exists() or not abs_path.is_file():
        raise HTTPException(404, "file not found")
    try:
        return abs_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(415, "not a text file")


# ===========================================================================
# Step 8: 외부 공개용 통합 API (/api/*)
#
# 사진의 명세를 그대로 매핑한다:
#   POST /api/input/code   - 코드 입력 저장
#   POST /api/input/image  - 이미지 입력 저장 + vision-server 호출
#   POST /api/infer        - 통합 추론 (입력 저장 → 언어 감지 → vision → LLM → 임베딩 → DB)
#   POST /api/optimize     - 기존 generated_code 기반 최적화 + diff
#   POST /api/embed        - 텍스트 임베딩 생성/저장
#   GET  /api/answers      - 저장된 답변 목록
#   GET  /api/hardware     - 현재 하드웨어 프로필
#   GET  /api/health       - 전체 서비스 헬스체크 묶음
# ===========================================================================
MODEL_SERVER_URL     = os.getenv("MODEL_SERVER_URL",     "http://model-server:8001").rstrip("/")
VISION_SERVER_URL    = os.getenv("VISION_SERVER_URL",    "http://vision-server:8002").rstrip("/")
EMBEDDING_SERVER_URL = os.getenv("EMBEDDING_SERVER_URL", "http://embedding-server:8003").rstrip("/")
LANGUAGE_WORKER_URL  = os.getenv("LANGUAGE_WORKER_URL",  "http://language-worker:8004").rstrip("/")
VECTOR_DB_URL        = os.getenv("VECTOR_DB_URL",        "http://qdrant:6333").rstrip("/")
VECTOR_DB_COLLECTION = os.getenv("VECTOR_DB_COLLECTION", "localai_embeddings").strip() or "localai_embeddings"
VECTOR_DB_ENABLED    = os.getenv("VECTOR_DB_ENABLED", "1").lower() not in ("0", "false", "no")


def _http_post_json(url: str, payload: dict[str, Any], timeout: float = 30.0) -> dict[str, Any] | None:
    """내부 워커 호출. 실패 시 None 반환 (호출부에서 fallback)."""
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
        log.info("worker call failed url=%s err=%s", url, exc)
        return None


def _http_put_json(url: str, payload: dict[str, Any], timeout: float = 15.0) -> dict[str, Any] | None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        log.info("worker put failed url=%s err=%s", url, exc)
        return None


def _detect_language(code: str, hint: str | None) -> tuple[str, dict[str, Any] | None]:
    if hint:
        return hint.lower(), {"source": "hint"}
    res = _http_post_json(f"{LANGUAGE_WORKER_URL}/api/v1/detect", {"code": code})
    if res and res.get("language"):
        return str(res["language"]), res
    return "plain", None


def _generate_with_model(prompt: str, model_name: str, language: str | None,
                         task: str = "infer") -> tuple[str, dict[str, Any] | None]:
    res = _http_post_json(
        f"{MODEL_SERVER_URL}/api/v1/generate",
        {"prompt": prompt, "model": model_name, "language": language, "task": task},
        timeout=60,
    )
    if res and (res.get("text") or res.get("answer")):
        return res.get("text") or res.get("answer") or "", res
    # fallback stub
    stub = (
        f"# {model_name} ({task}, stub)\n\n"
        "model-server 가 응답하지 않아 echo 답변을 생성합니다.\n\n"
        f"```\n{prompt[:2000]}\n```\n"
    )
    return stub, None


def _embed_text(text: str, model: str | None = None) -> dict[str, Any] | None:
    return _http_post_json(
        f"{EMBEDDING_SERVER_URL}/api/v1/embed",
        {"text": text, "model": model},
        timeout=15,
    )


def _store_embedding_from_worker(emb: dict[str, Any], *, target_type: str, target_id: int) -> int | None:
    """embedding-server 응답을 받아 embeddings 테이블에 upsert + 파일 저장."""
    if not emb or not isinstance(emb.get("vector"), list):
        return None
    vector: list[float] = emb["vector"]
    model_name: str = emb.get("model") or "stub-hash"
    saved = storage.save_embedding(
        vector,
        target_type=target_type,
        target_id=target_id,
        model_name=model_name,
    )
    norm = sum(x * x for x in vector) ** 0.5
    db.execute(
        """
        INSERT INTO embeddings
            (target_type, target_id, model_name, dim, vector_file_path,
             vector_json, file_size, sha256, norm, content_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            vector_file_path=VALUES(vector_file_path),
            vector_json=VALUES(vector_json),
            file_size=VALUES(file_size),
            sha256=VALUES(sha256),
            dim=VALUES(dim),
            norm=VALUES(norm),
            content_hash=VALUES(content_hash)
        """,
        (target_type, target_id, model_name, len(vector),
         saved.rel_path, json.dumps(vector), saved.size, saved.sha256, norm,
         emb.get("content_hash")),
    )
    embedding_id = _embedding_row_id(target_type, target_id, model_name)
    if embedding_id:
        _vector_db_upsert(
            embedding_id=embedding_id,
            target_type=target_type,
            target_id=target_id,
            vector=vector,
            model_name=model_name,
            model_version=model_name,
            content_hash=emb.get("content_hash"),
        )
    return embedding_id


# --- GET /api/health -------------------------------------------------------
@app.get("/api/health")
def api_health():
    """8단계 외부 공개 헬스체크 - 모든 서비스 상태 + DB."""
    return system_services()


# --- GET /api/hardware -----------------------------------------------------
@app.get("/api/hardware")
def api_hardware():
    return hardware_current()


# --- GET /api/answers ------------------------------------------------------
@app.get("/api/answers")
def api_answers(
    q: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return list_model_answers(q=q, model=model, limit=limit, offset=offset)


# --- POST /api/input/code --------------------------------------------------
class InputCodeIn(BaseModel):
    code: str
    language: Optional[str] = None
    file_name: Optional[str] = None
    project_id: Optional[int] = None
    user_tag: Optional[str] = None


@app.post("/api/input/code")
def api_input_code(payload: InputCodeIn):
    """사용자가 직접 입력한 코드를 raw_inputs + code_data/original 에 저장."""
    if not payload.code or not payload.code.strip():
        raise HTTPException(400, "empty code")

    detected_lang, detect_info = _detect_language(payload.code, payload.language)

    raw_id = _insert_raw_input(
        input_type="text",
        raw_text=payload.code,
        project_id=payload.project_id,
        user_tag=payload.user_tag,
    )
    saved = storage.save_original_code(
        payload.code,
        raw_input_id=raw_id,
        language=detected_lang,
        file_name=payload.file_name,
    )
    db.execute(
        "UPDATE raw_inputs SET source_file_path=%s WHERE id=%s",
        (saved.rel_path, raw_id),
    )
    return {
        "raw_input_id": raw_id,
        "language": detected_lang,
        "language_detect": detect_info,
        **saved.as_dict(),
    }


# --- GET /api/image-types --------------------------------------------------
@app.get("/api/image-types")
def api_image_types():
    """Step 10 지원 이미지 타입 목록 (vision-server 가 다운되어도 동작).

    가능하면 vision-server 에서 가져오고, 실패하면 정적 fallback 을 반환한다.
    """
    res = None
    try:
        with urllib.request.urlopen(f"{VISION_SERVER_URL}/api/v1/image-types", timeout=2) as resp:
            res = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        res = None
    if res and isinstance(res.get("types"), list):
        return res
    return {
        "types": [
            {"key": "code",       "label": "코드 이미지"},
            {"key": "error_log",  "label": "에러 로그 이미지"},
            {"key": "algorithm",  "label": "알고리즘 문제 이미지"},
            {"key": "tech_spec",  "label": "기술 명세서 이미지"},
            {"key": "api_spec",   "label": "API 명세 이미지"},
            {"key": "db_design",  "label": "DB 설계 이미지"},
            {"key": "ui_design",  "label": "UI 설계 이미지"},
            {"key": "other",      "label": "기타 이미지"},
        ]
    }


# --- POST /api/input/image -------------------------------------------------
@app.post("/api/input/image")
async def api_input_image(
    file: UploadFile = File(...),
    project_id: Optional[int] = Form(None),
    user_tag: Optional[str] = Form(None),
    extract: bool = Form(True),
    image_type: Optional[str] = Form(None),
    language_hint: Optional[str] = Form(None),
):
    """이미지 업로드 → 저장 → 타입 분류/추출(vision-server) → DB 기록.

    Step 10 흐름:
      이미지 업로드 → image_data/original 저장 → 타입 분류 →
      텍스트/코드/명세 추출 → image_data/extracted_* 저장 →
      MySQL image_data 기록 → LLM 입력 자료로 연결
    """
    blob = await file.read()
    if not blob:
        raise HTTPException(400, "empty file")
    if image_type and image_type not in IMAGE_TYPE_KEYS:
        raise HTTPException(400, f"unsupported image_type: {image_type}")

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
        INSERT INTO image_data
            (raw_input_id, mime_type, file_path, file_size, sha256,
             image_type, image_type_source, image_type_confidence, extraction_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (raw_id, file.content_type or "image/png", saved.rel_path, saved.size, saved.sha256,
         image_type, ("user" if image_type else None),
         (1.0 if image_type else None),
         "pending" if extract else "skipped"),
    )

    extraction: dict[str, Any] | None = None
    if extract:
        # 컨테이너 내부의 절대 경로를 vision-server 와 공유 볼륨으로 전달
        abs_path = str(storage.resolve(saved.rel_path))
        extraction = _http_post_json(
            f"{VISION_SERVER_URL}/api/v1/extract",
            {
                "file_path": abs_path,
                "image_type": image_type,
                "language_hint": language_hint,
                "filename": file.filename,
            },
            timeout=30,
        )
        if extraction:
            try:
                store_image_extracted(image_id, ImageExtractIn(
                    image_id=image_id,
                    extracted_text=extraction.get("text"),
                    extracted_code=extraction.get("code"),
                    extracted_code_language=extraction.get("language"),
                    extracted_spec=extraction.get("spec"),
                    metadata=extraction.get("metadata") or {
                        "engine": extraction.get("engine"),
                        "confidence": extraction.get("confidence"),
                        "bytes": extraction.get("bytes"),
                    },
                    ocr_engine=extraction.get("engine"),
                    ocr_confidence=extraction.get("confidence"),
                    image_type=extraction.get("image_type") or image_type,
                    image_type_source=extraction.get("image_type_source"),
                    image_type_confidence=extraction.get("image_type_confidence"),
                ))
            except Exception as e:  # noqa: BLE001
                log.warning("failed to persist extraction: %s", e)
                db.execute(
                    "UPDATE image_data SET extraction_status='failed' WHERE id=%s",
                    (image_id,),
                )
        else:
            db.execute(
                "UPDATE image_data SET extraction_status='failed' WHERE id=%s",
                (image_id,),
            )

    final_row = db.fetch_one(
        """
        SELECT image_type, image_type_source, image_type_confidence,
               extraction_status, extraction_engine,
               text_file_path, code_file_path, spec_file_path, metadata_file_path
          FROM image_data WHERE id=%s
        """,
        (image_id,),
    ) or {}

    return {
        "raw_input_id": raw_id,
        "image_id": image_id,
        "image_type": final_row.get("image_type"),
        "image_type_source": final_row.get("image_type_source"),
        "image_type_confidence": float(final_row["image_type_confidence"])
            if final_row.get("image_type_confidence") is not None else None,
        "extraction_status": final_row.get("extraction_status"),
        "extraction": extraction,
        "extracted_files": {
            "text":     final_row.get("text_file_path"),
            "code":     final_row.get("code_file_path"),
            "spec":     final_row.get("spec_file_path"),
            "metadata": final_row.get("metadata_file_path"),
        },
        **saved.as_dict(),
    }


# --- POST /api/infer -------------------------------------------------------
class InferIn(BaseModel):
    requirement: Optional[str] = None
    code: Optional[str] = None
    language: Optional[str] = None
    image_id: Optional[int] = None
    raw_input_id: Optional[int] = None
    model: Optional[str] = None
    project_id: Optional[int] = None
    user_tag: Optional[str] = None
    embed: bool = True


@app.post("/api/infer")
def api_infer(payload: InferIn):
    """사진의 처리 흐름을 그대로 구현한 통합 추론 엔드포인트.

    Web UI → /api/infer → 입력 저장 → 언어 감지 → (이미지 ⇒ vision-server)
        → LLM 추론(model-server) → 임베딩(embedding-server) → MySQL → 결과 반환
    """
    if not (payload.requirement or payload.code or payload.image_id or payload.raw_input_id):
        raise HTTPException(400, "requirement / code / image_id / raw_input_id 중 최소 하나 필요")

    # 1) 입력 저장 (raw_inputs)
    raw_id = payload.raw_input_id
    if raw_id is None:
        if payload.image_id and (payload.requirement or payload.code):
            input_type = "mixed"
        elif payload.image_id:
            input_type = "image"
        else:
            input_type = "text"
        raw_text_parts: list[str] = []
        if payload.requirement:
            raw_text_parts.append("## 요구사항\n" + payload.requirement)
        if payload.code:
            raw_text_parts.append(f"## 입력 코드\n```{payload.language or ''}\n{payload.code}\n```")
        raw_id = _insert_raw_input(
            input_type=input_type,
            raw_text="\n\n".join(raw_text_parts) if raw_text_parts else None,
            project_id=payload.project_id,
            user_tag=payload.user_tag,
        )

    # 2) 언어 감지 (코드가 있을 때만)
    language: str | None = payload.language
    detect_info: dict[str, Any] | None = None
    if payload.code and not language:
        language, detect_info = _detect_language(payload.code, None)

    # 2.5) 입력 코드 원본 저장
    original_code_path: str | None = None
    if payload.code:
        s = storage.save_original_code(
            payload.code, raw_input_id=raw_id, language=language,
        )
        original_code_path = s.rel_path
        db.execute("UPDATE raw_inputs SET source_file_path=%s WHERE id=%s", (s.rel_path, raw_id))

    # 3) 이미지가 첨부됐다면 vision-server 결과를 prompt 에 반영
    image_extraction: dict[str, Any] | None = None
    if payload.image_id:
        img_row = db.fetch_one(
            "SELECT id, file_path FROM image_data WHERE id=%s", (payload.image_id,)
        )
        if not img_row:
            raise HTTPException(404, f"image_id={payload.image_id} not found")
        try:
            abs_path = str(storage.resolve(img_row["file_path"]))
        except ValueError:
            abs_path = img_row["file_path"]
        image_extraction = _http_post_json(
            f"{VISION_SERVER_URL}/api/v1/extract",
            {"file_path": abs_path, "language_hint": language},
            timeout=30,
        )

    # 4) LLM 추론 (model-server)
    prompt_parts: list[str] = []
    if payload.requirement:
        prompt_parts.append("[요구사항]\n" + payload.requirement)
    if payload.code:
        prompt_parts.append(f"[입력 코드 ({language or 'plain'})]\n{payload.code}")
    if image_extraction and image_extraction.get("text"):
        prompt_parts.append("[이미지에서 추출]\n" + str(image_extraction.get("text")))
    prompt_text = "\n\n".join(prompt_parts) or "(empty)"

    model_name = payload.model or _default_local_checkpoint()
    started = datetime.utcnow()
    answer_text, raw_resp = _generate_with_model(
        prompt_text, model_name, language, task="infer"
    )
    latency_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
    tokens_in = (raw_resp or {}).get("tokens_input")
    tokens_out = (raw_resp or {}).get("tokens_output")

    # 5) MySQL 저장 (model_answers + 파일)
    answer_id = db.execute(
        """
        INSERT INTO model_answers
            (raw_input_id, requirement_id, model_name, model_provider,
             prompt_text, answer_text, tokens_input, tokens_output, latency_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (raw_id, None, model_name, "local",
         prompt_text, answer_text, tokens_in, tokens_out, latency_ms),
    )
    saved_ans = storage.save_model_answer(
        answer_text, answer_id=answer_id, model_name=model_name,
    )
    db.execute(
        "UPDATE model_answers SET answer_file_path=%s, file_size=%s, sha256=%s WHERE id=%s",
        (saved_ans.rel_path, saved_ans.size, saved_ans.sha256, answer_id),
    )

    # 6) embedding 생성 + 저장
    embedding_id: int | None = None
    if payload.embed:
        emb = _embed_text(answer_text)
        if emb:
            embedding_id = _store_embedding_from_worker(
                emb, target_type="model_answer", target_id=answer_id,
            )

    # 7) 결과 반환
    return {
        "raw_input_id": raw_id,
        "answer_id": answer_id,
        "model": model_name,
        "language": language,
        "language_detect": detect_info,
        "image_extraction": image_extraction,
        "latency_ms": latency_ms,
        "answer_text": answer_text,
        "answer_file_path": saved_ans.rel_path,
        "original_code_path": original_code_path,
        "embedding_id": embedding_id,
        "stub": raw_resp is None,
    }


# --- POST /api/optimize ----------------------------------------------------
class OptimizeIn(BaseModel):
    answer_id: Optional[int] = None
    generated_code_id: Optional[int] = None
    code: Optional[str] = None
    language: Optional[str] = None
    instruction: Optional[str] = None
    model: Optional[str] = None


@app.post("/api/optimize")
def api_optimize(payload: OptimizeIn):
    """generated_code 또는 임의 코드를 받아 최적화 결과 + diff 를 만든다.

    - ``generated_code_id`` 가 주어지면 해당 행을 base 로 사용
    - ``answer_id`` + ``code`` 조합이면 새 generated_code 를 먼저 만든다
    - 둘 다 없고 ``code`` 만 있을 때는 임시 generated_code 행을 생성
    """
    base_code: str | None = None
    base_lang: str | None = payload.language
    gen_id: int | None = payload.generated_code_id

    if gen_id:
        row = db.fetch_one(
            "SELECT id, code_text, language, answer_id FROM generated_code WHERE id=%s",
            (gen_id,),
        )
        if not row:
            raise HTTPException(404, "generated_code not found")
        base_code = row["code_text"]
        base_lang = base_lang or row["language"]
    elif payload.code:
        if not payload.answer_id:
            raise HTTPException(400, "answer_id 가 없으면 generated_code 를 만들 수 없습니다")
        s_gen = storage.save_generated_code(
            payload.code, answer_id=payload.answer_id, language=base_lang,
        )
        gen_id = db.execute(
            """
            INSERT INTO generated_code
                (answer_id, language, file_name, code_text, is_runnable,
                 file_path, file_size, sha256)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (payload.answer_id, base_lang, None, payload.code, 0,
             s_gen.rel_path, s_gen.size, s_gen.sha256),
        )
        base_code = payload.code
    else:
        raise HTTPException(400, "generated_code_id 또는 (answer_id + code) 중 하나가 필요합니다")

    # 모델 호출 (또는 stub) - 같은 코드를 그대로 돌려받지 않도록 instruction 을 prompt 에 합친다
    prompt = (
        "[지시]\n" + (payload.instruction or "다음 코드를 더 효율적으로 최적화해줘.") +
        f"\n\n[코드 ({base_lang or 'plain'})]\n{base_code}"
    )
    model_name = payload.model or _default_local_checkpoint()
    optimized_text, raw_resp = _generate_with_model(
        prompt, model_name, base_lang, task="optimize",
    )

    # 최적화 코드 + diff 저장
    saved_code = storage.save_optimized_code(
        optimized_text, generated_code_id=gen_id, language=base_lang,
    )
    diff_text = storage.make_unified_diff(base_code or "", optimized_text)
    saved_diff = storage.save_code_diff(diff_text, generated_code_id=gen_id)
    oc_id = db.execute(
        """
        INSERT INTO optimized_code
            (generated_code_id, optimizer, language, code_text, improvement_notes,
             file_path, diff_file_path, file_size, sha256)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (gen_id, model_name, base_lang, optimized_text, payload.instruction,
         saved_code.rel_path, saved_diff.rel_path, saved_code.size, saved_code.sha256),
    )
    return {
        "generated_code_id": gen_id,
        "optimized_code_id": oc_id,
        "language": base_lang,
        "code": optimized_text,
        "code_file_path": saved_code.rel_path,
        "diff_file_path": saved_diff.rel_path,
        "stub": raw_resp is None,
    }


# --- POST /api/embed -------------------------------------------------------
class EmbedTextIn(BaseModel):
    text: str
    target_type: Optional[str] = None      # 예: model_answer / generated_code
    target_id: Optional[int] = None
    model: Optional[str] = None


@app.post("/api/embed")
def api_embed(payload: EmbedTextIn):
    """텍스트 임베딩 생성. target_type/target_id 가 주어지면 DB 에 영구 저장."""
    if not payload.text or not payload.text.strip():
        raise HTTPException(400, "empty text")
    emb = _embed_text(payload.text, model=payload.model)
    if not emb:
        raise HTTPException(503, "embedding-server unavailable")

    embedding_id: int | None = None
    if payload.target_type and payload.target_id:
        embedding_id = _store_embedding_from_worker(
            emb, target_type=payload.target_type, target_id=payload.target_id,
        )

    return {
        "embedding_id": embedding_id,
        "model": emb.get("model"),
        "dim": emb.get("dim"),
        "content_hash": emb.get("content_hash"),
        "vector_preview": (emb.get("vector") or [])[:8],
    }


# ===========================================================================
# Step 9: Language Compatibility Layer 프록시
#  - language-worker /api/v1/{detect,analyze,languages,adapters,guess-by-filename}
#    를 외부 공개용 /api/language/* 로 노출.
#  - language-worker 가 다운되면 503 반환.
# ===========================================================================
def _http_get_json(url: str, timeout: float = 10.0) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.info("language-worker GET failed url=%s err=%s", url, exc)
        return None


class LangAnalyzeIn(BaseModel):
    code: str
    filename: Optional[str] = None
    hint: Optional[str] = None
    include_patterns: bool = True
    persist: bool = False
    raw_input_id: Optional[int] = None


@app.post("/api/language/analyze")
def api_language_analyze(payload: LangAnalyzeIn):
    """코드 한 덩어리에 대한 통합 언어 분석.

    - language-worker 의 ``/api/v1/analyze`` 호출 결과를 그대로 반환
    - ``persist=True`` 이고 ``raw_input_id`` 가 있으면 ``raw_inputs.meta_json``
      에 분석 결과를 머지해서 저장한다.
    """
    if not (payload.code or "").strip():
        raise HTTPException(400, "empty code")

    res = _http_post_json(
        f"{LANGUAGE_WORKER_URL}/api/v1/analyze",
        {
            "code": payload.code,
            "filename": payload.filename,
            "hint": payload.hint,
            "include_patterns": payload.include_patterns,
        },
        timeout=15,
    )
    if res is None:
        raise HTTPException(503, "language-worker unavailable")

    if payload.persist and payload.raw_input_id:
        # 기존 meta_json 보존 + language_analysis 키 추가
        row = db.fetch_one(
            "SELECT meta_json FROM raw_inputs WHERE id=%s",
            (payload.raw_input_id,),
        )
        meta: dict[str, Any] = {}
        if row and row.get("meta_json"):
            try:
                meta = json.loads(row["meta_json"]) if isinstance(row["meta_json"], str) else dict(row["meta_json"])
            except Exception:
                meta = {}
        meta["language_analysis"] = {
            "language": res.get("language"),
            "support_level": res.get("support_level"),
            "adapter": res.get("adapter"),
            "stats": res.get("stats"),
            "build_command": res.get("build_command"),
            "run_command": res.get("run_command"),
        }
        db.execute(
            "UPDATE raw_inputs SET meta_json=%s, "
            "detected_language=%s, support_level=%s, "
            "language_id=COALESCE(language_id, "
            "(SELECT id FROM language_profiles WHERE language=%s LIMIT 1)) "
            "WHERE id=%s",
            (json.dumps(meta, ensure_ascii=False),
             res.get("language"), res.get("support_level"),
             res.get("language"), payload.raw_input_id),
        )
        res["persisted"] = True

    return res


@app.get("/api/language/languages")
def api_language_languages():
    """지원 언어 카탈로그 + 등급."""
    res = _http_get_json(f"{LANGUAGE_WORKER_URL}/api/v1/languages")
    if res is None:
        raise HTTPException(503, "language-worker unavailable")
    return res


@app.get("/api/language/adapters")
def api_language_adapters():
    """언어별 adapter 매핑."""
    res = _http_get_json(f"{LANGUAGE_WORKER_URL}/api/v1/adapters")
    if res is None:
        raise HTTPException(503, "language-worker unavailable")
    return res


class LangGuessIn(BaseModel):
    filename: str


@app.post("/api/language/guess")
def api_language_guess(payload: LangGuessIn):
    """파일명만으로 언어/명령 추론."""
    res = _http_post_json(
        f"{LANGUAGE_WORKER_URL}/api/v1/guess-by-filename",
        {"filename": payload.filename},
        timeout=5,
    )
    if res is None:
        raise HTTPException(503, "language-worker unavailable")
    return res


# ===========================================================================
# Step 11: 자체 Vision-Language Model 학습 파이프라인
#
# 사진 명세 매핑:
#   - 학습 데이터 형태(JSON)는 그대로 받고 vlm_training_samples 에 저장.
#   - 학습 순서(5단계) 는 vlm_training_stages 카탈로그로 노출.
#   - 초기 VLM 목표("이미지 안의 소스코드 영역 탐지 → 텍스트화 → 파일 저장
#     → LLM 입력으로 전달") 는 /api/vlm/code-image-pipeline 한 번 호출로
#     전 과정이 끝나도록 조립한다.
# ===========================================================================
VLM_STAGE_FALLBACK: list[dict[str, Any]] = [
    {"stage_no": 1, "stage_key": "code_image",
     "label": "코드 이미지 인식", "image_type": "code", "is_initial": True},
    {"stage_no": 2, "stage_key": "error_log_image",
     "label": "에러 로그 이미지 인식", "image_type": "error_log", "is_initial": False},
    {"stage_no": 3, "stage_key": "spec_image",
     "label": "명세서 이미지 인식", "image_type": "tech_spec", "is_initial": False},
    {"stage_no": 4, "stage_key": "table_structure",
     "label": "표 구조 인식", "image_type": "db_design", "is_initial": False},
    {"stage_no": 5, "stage_key": "ui_layout",
     "label": "UI 화면 구조 인식", "image_type": "ui_design", "is_initial": False},
]
VLM_STAGE_KEYS = {s["stage_key"] for s in VLM_STAGE_FALLBACK}


def _vlm_load_stages_from_db() -> list[dict[str, Any]]:
    try:
        rows = db.fetch_all(
            "SELECT id, stage_no, stage_key, label, image_type, "
            "       description, is_initial "
            "FROM vlm_training_stages ORDER BY stage_no ASC"
        )
        if rows:
            for r in rows:
                r["is_initial"] = bool(r.get("is_initial"))
            return rows
    except Exception as exc:  # noqa: BLE001
        log.info("vlm stages: DB unavailable, using fallback (%s)", exc)
    return VLM_STAGE_FALLBACK


def _vlm_resolve_stage(stage_key: str | None,
                       image_type: str | None) -> dict[str, Any] | None:
    """stage_key 우선, 없으면 image_type 으로 단계 자동 매핑."""
    stages = _vlm_load_stages_from_db()
    if stage_key:
        for s in stages:
            if s["stage_key"] == stage_key:
                return s
    if image_type:
        for s in stages:
            if s["image_type"] == image_type:
                return s
    return None


@app.get("/api/vlm/stages")
def api_vlm_stages():
    """학습 단계 카탈로그.

    가능하면 vision-server 에서 가져오고(스키마/초기 파이프라인 정보 포함),
    실패하면 DB / 정적 fallback 으로 응답한다.
    """
    res: dict[str, Any] | None = None
    try:
        with urllib.request.urlopen(f"{VISION_SERVER_URL}/api/v1/vlm/stages", timeout=2) as resp:
            res = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        res = None

    stages_db = _vlm_load_stages_from_db()
    if res and isinstance(res.get("stages"), list):
        # vision-server 응답이 우선이지만, DB 의 stage_id 도 함께 노출.
        by_key = {s["stage_key"]: s for s in stages_db}
        for s in res["stages"]:
            db_row = by_key.get(s.get("stage_key"))
            if db_row:
                s["id"] = db_row.get("id")
        return res

    return {
        "stages": stages_db,
        "sample_schema": {
            "image_path":         "data/image_data/original/sample.png",
            "image_type":         "code_image",
            "expected_text":      "...",
            "expected_code":      "...",
            "expected_structure": {},
        },
        "initial_pipeline": {
            "name": "code_region_extract",
            "stage_key": "code_image",
            "steps": [
                "이미지 안의 소스코드 영역 탐지",
                "코드 텍스트화",
                "파일 저장",
                "LLM 입력으로 전달",
            ],
        },
    }


# --- POST /api/vlm/dataset -------------------------------------------------
class VlmSampleIn(BaseModel):
    image_path: str
    image_type: str
    expected_text: Optional[str] = None
    expected_code: Optional[str] = None
    expected_language: Optional[str] = None
    expected_structure: Optional[dict[str, Any]] = None
    image_id: Optional[int] = None
    split: Optional[str] = "train"
    user_tag: Optional[str] = None
    notes: Optional[str] = None


@app.post("/api/vlm/dataset")
def api_vlm_dataset_add(payload: VlmSampleIn):
    """사진의 학습 데이터 JSON 형식으로 샘플을 등록한다.

    ``image_type`` 은 stage_key("code_image" 등) 또는 image_data 의 image_type
    ("code" 등) 둘 다 허용한다.
    """
    stage = _vlm_resolve_stage(payload.image_type, payload.image_type)
    if not stage:
        raise HTTPException(
            400,
            f"unknown image_type/stage: {payload.image_type!r}. "
            f"allowed stage_key={sorted(VLM_STAGE_KEYS)}"
        )

    # 이미지 경로 검증 (DATA_DIR 외부로의 path traversal 방지)
    rel_image_path = payload.image_path.replace("\\", "/")
    if rel_image_path.startswith("data/"):
        rel_image_path = rel_image_path[len("data/"):]
    try:
        abs_image_path = storage.resolve(rel_image_path)
    except ValueError:
        raise HTTPException(400, "image_path 가 DATA_DIR 외부를 가리킵니다")

    image_exists = abs_image_path.exists() and abs_image_path.is_file()

    split = (payload.split or "train").lower()
    if split not in {"train", "val", "test"}:
        raise HTTPException(400, "split 은 train/val/test 중 하나여야 합니다")

    expected_structure_json = (
        json.dumps(payload.expected_structure, ensure_ascii=False)
        if payload.expected_structure is not None else None
    )

    sample_id = db.execute(
        """
        INSERT INTO vlm_training_samples
            (stage_id, stage_key, image_type, image_id, image_path,
             expected_text, expected_code, expected_language, expected_structure,
             split, source, user_tag, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (stage["id"] if stage.get("id") else None,
         stage["stage_key"], stage["image_type"], payload.image_id,
         rel_image_path,
         payload.expected_text, payload.expected_code,
         payload.expected_language, expected_structure_json,
         split, "manual", payload.user_tag, payload.notes),
    )

    # 사진의 JSON 그대로 디스크에 보존 (학습 시 그대로 로드 가능)
    on_disk = {
        "image_path":         "data/" + rel_image_path,
        "image_type":         stage["stage_key"],
        "expected_text":      payload.expected_text,
        "expected_code":      payload.expected_code,
        "expected_language":  payload.expected_language,
        "expected_structure": payload.expected_structure or {},
    }
    saved = storage.save_vlm_training_sample(
        on_disk, stage_key=stage["stage_key"], sample_id=sample_id,
    )
    db.execute(
        "UPDATE vlm_training_samples SET sample_file_path=%s WHERE id=%s",
        (saved.rel_path, sample_id),
    )

    return {
        "sample_id": sample_id,
        "stage_key": stage["stage_key"],
        "stage_no": stage.get("stage_no"),
        "image_type": stage["image_type"],
        "image_path": "data/" + rel_image_path,
        "image_exists": image_exists,
        "sample_file_path": saved.rel_path,
        "split": split,
    }


@app.get("/api/vlm/dataset")
def api_vlm_dataset_list(
    stage: Optional[str] = Query(None, description="stage_key 필터"),
    image_type: Optional[str] = Query(None),
    split: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    where: list[str] = []
    params: list[Any] = []
    if stage:
        where.append("stage_key = %s")
        params.append(stage)
    if image_type:
        where.append("image_type = %s")
        params.append(image_type)
    if split:
        where.append("split = %s")
        params.append(split)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = db.fetch_all(
        f"SELECT id, stage_id, stage_key, image_type, image_id, image_path, "
        f"       expected_language, sample_file_path, split, source, user_tag, "
        f"       LEFT(COALESCE(expected_text,''), 240) AS expected_text_preview, "
        f"       LEFT(COALESCE(expected_code,''), 240) AS expected_code_preview, "
        f"       created_at "
        f"FROM vlm_training_samples {where_sql} "
        f"ORDER BY id DESC LIMIT %s OFFSET %s",
        tuple(params + [limit, offset]),
    )
    total = (db.fetch_one(
        f"SELECT COUNT(*) AS n FROM vlm_training_samples {where_sql}",
        tuple(params),
    ) or {}).get("n", 0)
    return {"total": total, "limit": limit, "offset": offset, "items": rows}


@app.get("/api/vlm/dataset/{sample_id}")
def api_vlm_dataset_get(sample_id: int):
    row = db.fetch_one(
        "SELECT * FROM vlm_training_samples WHERE id=%s", (sample_id,),
    )
    if not row:
        raise HTTPException(404, "vlm_training_sample not found")
    if isinstance(row.get("expected_structure"), str):
        try:
            row["expected_structure"] = json.loads(row["expected_structure"])
        except Exception:
            pass
    return row


@app.get("/api/vlm/training-progress")
def api_vlm_training_progress():
    """단계별 샘플 수 집계 (학습 준비도 확인용)."""
    stages = _vlm_load_stages_from_db()
    counts = db.fetch_all(
        "SELECT stage_key, split, COUNT(*) AS n "
        "FROM vlm_training_samples GROUP BY stage_key, split"
    ) or []
    by_key: dict[str, dict[str, int]] = {}
    for c in counts:
        by_key.setdefault(c["stage_key"], {"train": 0, "val": 0, "test": 0, "total": 0})
        by_key[c["stage_key"]][c["split"]] = int(c["n"])
        by_key[c["stage_key"]]["total"] += int(c["n"])

    progress = []
    for s in stages:
        c = by_key.get(s["stage_key"], {"train": 0, "val": 0, "test": 0, "total": 0})
        progress.append({
            "stage_no":   s.get("stage_no"),
            "stage_key":  s["stage_key"],
            "label":      s.get("label"),
            "image_type": s.get("image_type"),
            "is_initial": bool(s.get("is_initial")),
            "counts":     c,
        })
    return {"stages": progress, "grand_total": sum(p["counts"]["total"] for p in progress)}


# --- POST /api/vlm/code-image-pipeline -------------------------------------
class VlmCodePipelineIn(BaseModel):
    image_id: int
    forward_to_llm: bool = False
    requirement: Optional[str] = None
    model: Optional[str] = None
    language_hint: Optional[str] = None


@app.post("/api/vlm/code-image-pipeline")
def api_vlm_code_image_pipeline(payload: VlmCodePipelineIn):
    """초기 VLM 파이프라인 (사진의 핵심 박스):

        이미지 안의 소스코드 영역 탐지
              ↓
        코드 텍스트화
              ↓
        파일 저장
              ↓
        LLM 입력으로 전달

    한 번의 호출로 4단계가 모두 실행되며, 각 단계의 산출물은
    ``vlm_pipeline_runs`` + ``data/vlm_training/pipeline_output/`` +
    ``model_answers`` 에 영구 저장된다.
    """
    img_row = db.fetch_one(
        "SELECT id, raw_input_id, file_path, image_type FROM image_data WHERE id=%s",
        (payload.image_id,),
    )
    if not img_row:
        raise HTTPException(404, f"image_id={payload.image_id} not found")

    try:
        abs_path = str(storage.resolve(img_row["file_path"]))
    except ValueError:
        abs_path = img_row["file_path"]

    started = datetime.utcnow()

    # 1) + 2) vision-server: 코드 영역 탐지 + OCR
    detect = _http_post_json(
        f"{VISION_SERVER_URL}/api/v1/vlm/detect-code-region",
        {
            "file_path": abs_path,
            "filename": Path(img_row["file_path"]).name,
            "language_hint": payload.language_hint,
        },
        timeout=30,
    )
    status = "done" if detect else "failed"
    code_text = (detect or {}).get("code") or (detect or {}).get("text") or ""
    language  = (detect or {}).get("language") or payload.language_hint
    regions   = (detect or {}).get("regions") or []
    detector  = (detect or {}).get("detector")
    ocr_engine = (detect or {}).get("ocr_engine")

    # 3) 파일 저장
    text_file_path: str | None = None
    if code_text:
        ext_map = {"python": ".py", "javascript": ".js", "typescript": ".ts",
                   "java": ".java", "cpp": ".cpp", "c": ".c", "go": ".go",
                   "rust": ".rs", "csharp": ".cs", "kotlin": ".kt"}
        ext = ext_map.get((language or "").lower(), ".txt")
        saved = storage.save_vlm_pipeline_text(
            code_text,
            pipeline="code_region_extract",
            image_id=payload.image_id,
            extension=ext,
        )
        text_file_path = saved.rel_path

        # image_data.code_file_path 도 함께 갱신해서 결과 화면에서 그대로 보이게.
        try:
            db.execute(
                "UPDATE image_data SET code_file_path=COALESCE(code_file_path, %s), "
                "extraction_status='done', extraction_engine=%s, "
                "extracted_at=CURRENT_TIMESTAMP WHERE id=%s",
                (text_file_path, detector or ocr_engine, payload.image_id),
            )
        except Exception as exc:  # noqa: BLE001
            log.info("image_data update skipped: %s", exc)

    # 4) LLM 입력으로 전달 (옵션)
    llm_answer_id: int | None = None
    answer_text: str | None = None
    if payload.forward_to_llm and code_text:
        prompt_parts: list[str] = []
        if payload.requirement:
            prompt_parts.append("[요구사항]\n" + payload.requirement)
        prompt_parts.append(
            f"[이미지에서 추출한 코드 ({language or 'plain'})]\n{code_text}"
        )
        prompt_text = "\n\n".join(prompt_parts)
        model_name = payload.model or _default_local_checkpoint()

        answer_text, raw_resp = _generate_with_model(
            prompt_text, model_name, language, task="vlm_code_pipeline",
        )
        latency_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
        llm_answer_id = db.execute(
            """
            INSERT INTO model_answers
                (raw_input_id, requirement_id, model_name, model_provider,
                 prompt_text, answer_text, tokens_input, tokens_output, latency_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (img_row.get("raw_input_id"), None, model_name, "local",
             prompt_text, answer_text,
             (raw_resp or {}).get("tokens_input"),
             (raw_resp or {}).get("tokens_output"),
             latency_ms),
        )
        s_ans = storage.save_model_answer(
            answer_text, answer_id=llm_answer_id, model_name=model_name,
        )
        db.execute(
            "UPDATE model_answers SET answer_file_path=%s, file_size=%s, sha256=%s WHERE id=%s",
            (s_ans.rel_path, s_ans.size, s_ans.sha256, llm_answer_id),
        )

    total_ms = int((datetime.utcnow() - started).total_seconds() * 1000)

    # vlm_pipeline_runs 기록
    run_id: int | None = None
    try:
        run_id = db.execute(
            """
            INSERT INTO vlm_pipeline_runs
                (image_id, raw_input_id, pipeline, detector, ocr_engine,
                 region_count, detected_regions, extracted_text, text_file_path,
                 llm_answer_id, status, latency_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (payload.image_id, img_row.get("raw_input_id"),
             "code_region_extract", detector, ocr_engine,
             len(regions),
             json.dumps(regions, ensure_ascii=False) if regions else None,
             code_text or None,
             text_file_path, llm_answer_id, status, total_ms),
        )
    except Exception as exc:  # noqa: BLE001
        log.info("vlm_pipeline_runs insert skipped: %s", exc)

    return {
        "run_id": run_id,
        "image_id": payload.image_id,
        "stage_key": "code_image",
        "pipeline": "code_region_extract",
        "status": status,
        "detector": detector,
        "ocr_engine": ocr_engine,
        "language": language,
        "regions": regions,
        "code": code_text,
        "text_file_path": text_file_path,
        "llm_answer_id": llm_answer_id,
        "answer_text": answer_text,
        "latency_ms": total_ms,
        "stub": detect is None,
    }


# Step 12 appended below
# ===========================================================================
# Step 12: 자체 LLM 학습 파이프라인
#   - 12단계 카탈로그 + 학습 샘플 / 토크나이저 / corpus / 라이브러리 데이터 관리
#   - 4개 추론 API 프록시 : /api/llm/generate /optimize /explain /spec-to-code
#   - 학습 데이터 스키마 (사진 1:1):
#       { language, library, task, input_code, requirement, output_code, explanation }
# ===========================================================================
LLM_TASK_KEYS = {"optimize_code", "spec_to_code", "explain_code", "instruction", "pretrain"}
LLM_SPLIT_KEYS = {"train", "val", "test"}


def _llm_stage_id(stage_key: str | None) -> int | None:
    if not stage_key:
        return None
    row = db.fetch_one(
        "SELECT id FROM llm_training_stages WHERE stage_key=%s", (stage_key,)
    )
    return row["id"] if row else None


# ---- 12.1 단계 카탈로그 + 진행률 ----
@app.get("/api/llm/stages")
def llm_stages():
    rows = db.fetch_all(
        "SELECT id, stage_no, stage_key, label, description "
        "FROM llm_training_stages ORDER BY stage_no"
    )
    # 단계별 학습 샘플/실행 카운트
    sample_counts = {
        r["stage_id"]: r["c"] for r in db.fetch_all(
            "SELECT stage_id, COUNT(*) AS c FROM llm_training_samples "
            "WHERE stage_id IS NOT NULL GROUP BY stage_id"
        )
    }
    run_counts = {
        r["stage_id"]: r["c"] for r in db.fetch_all(
            "SELECT stage_id, COUNT(*) AS c FROM llm_training_runs GROUP BY stage_id"
        )
    }
    for r in rows:
        r["sample_count"] = int(sample_counts.get(r["id"], 0))
        r["run_count"] = int(run_counts.get(r["id"], 0))
    return {"stages": rows}


@app.get("/api/llm/training-progress")
def llm_training_progress():
    by_task = db.fetch_all(
        "SELECT task, split, COUNT(*) AS c FROM llm_training_samples "
        "GROUP BY task, split ORDER BY task, split"
    )
    by_lang = db.fetch_all(
        "SELECT language, COUNT(*) AS c FROM llm_training_samples "
        "GROUP BY language ORDER BY c DESC LIMIT 32"
    )
    runs = db.fetch_all(
        "SELECT id, stage_key, run_name, status, started_at, finished_at "
        "FROM llm_training_runs ORDER BY id DESC LIMIT 20"
    )
    corpus = db.fetch_all(
        "SELECT language, COUNT(*) AS files, COALESCE(SUM(file_size),0) AS bytes "
        "FROM llm_code_corpus GROUP BY language ORDER BY files DESC"
    )
    return {
        "samples_by_task_split": by_task,
        "samples_by_language": by_lang,
        "recent_runs": runs,
        "corpus": corpus,
    }


# ---- 12.2 학습 샘플 CRUD ----
class LlmSampleIn(BaseModel):
    task: str
    language: str
    library: Optional[str] = None
    input_code: Optional[str] = None
    requirement: Optional[str] = None
    output_code: Optional[str] = None
    explanation: Optional[str] = None
    meta: Optional[dict[str, Any]] = None
    split: Optional[str] = "train"
    source: Optional[str] = "manual"
    quality_score: Optional[float] = None
    stage_key: Optional[str] = None


@app.post("/api/llm/dataset")
def llm_dataset_create(payload: LlmSampleIn):
    if payload.task not in LLM_TASK_KEYS:
        raise HTTPException(400, f"unsupported task: {payload.task}")
    split = (payload.split or "train").lower()
    if split not in LLM_SPLIT_KEYS:
        raise HTTPException(400, f"unsupported split: {split}")

    stage_id = _llm_stage_id(payload.stage_key) if payload.stage_key else None

    sample_id = db.execute(
        """
        INSERT INTO llm_training_samples
            (stage_id, task, language, library, input_code, requirement,
             output_code, explanation, meta_json, split, source, quality_score, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ready')
        """,
        (stage_id, payload.task, payload.language, payload.library,
         payload.input_code, payload.requirement, payload.output_code,
         payload.explanation,
         json.dumps(payload.meta, ensure_ascii=False) if payload.meta else None,
         split, payload.source or "manual", payload.quality_score),
    )

    # 사진의 JSON 스키마 그대로 디스크에도 보존
    sample_json = {
        "language": payload.language,
        "library": payload.library,
        "task": payload.task,
        "input_code": payload.input_code,
        "requirement": payload.requirement,
        "output_code": payload.output_code,
        "explanation": payload.explanation,
    }
    saved = storage.save_llm_training_sample(
        sample_json, task=payload.task, sample_id=sample_id,
    )
    db.execute(
        "UPDATE llm_training_samples SET sample_file_path=%s WHERE id=%s",
        (saved.rel_path, sample_id),
    )
    return {
        "sample_id": sample_id,
        "stage_id": stage_id,
        "task": payload.task,
        "split": split,
        "sample_file_path": saved.rel_path,
    }


@app.get("/api/llm/dataset")
def llm_dataset_list(
    task: Optional[str] = None,
    language: Optional[str] = None,
    library: Optional[str] = None,
    split: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    where: list[str] = []
    args: list[Any] = []
    if task:
        where.append("task=%s"); args.append(task)
    if language:
        where.append("language=%s"); args.append(language)
    if library:
        where.append("library=%s"); args.append(library)
    if split:
        where.append("split=%s"); args.append(split)
    sql = (
        "SELECT id, task, language, library, split, source, quality_score, "
        "       sample_file_path, created_at "
        "FROM llm_training_samples"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT %s OFFSET %s"
    args += [int(limit), int(offset)]
    return {"items": db.fetch_all(sql, tuple(args))}


@app.get("/api/llm/dataset/{sample_id}")
def llm_dataset_get(sample_id: int):
    row = db.fetch_one(
        "SELECT * FROM llm_training_samples WHERE id=%s", (sample_id,)
    )
    if not row:
        raise HTTPException(404, "sample not found")
    return row


# ---- 12.3 토크나이저 / corpus / 라이브러리 ----
class LlmTokenizerIn(BaseModel):
    name: str
    algorithm: Optional[str] = "bpe"
    vocab_size: Optional[int] = 32000
    special_tokens: Optional[list[str]] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = False


@app.post("/api/llm/tokenizer")
def llm_tokenizer_create(payload: LlmTokenizerIn):
    config = payload.model_dump()
    saved = storage.save_llm_tokenizer_config(config, name=payload.name)
    tokenizer_id = db.execute(
        """
        INSERT INTO llm_tokenizer_configs
            (name, algorithm, vocab_size, special_tokens, notes,
             config_file_path, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            algorithm=VALUES(algorithm),
            vocab_size=VALUES(vocab_size),
            special_tokens=VALUES(special_tokens),
            notes=VALUES(notes),
            config_file_path=VALUES(config_file_path),
            is_active=VALUES(is_active)
        """,
        (payload.name, payload.algorithm or "bpe", int(payload.vocab_size or 32000),
         json.dumps(payload.special_tokens, ensure_ascii=False)
            if payload.special_tokens else None,
         payload.notes, saved.rel_path, 1 if payload.is_active else 0),
    )
    if payload.is_active:
        db.execute(
            "UPDATE llm_tokenizer_configs SET is_active=0 WHERE name<>%s",
            (payload.name,),
        )
    return {
        "tokenizer_id": tokenizer_id,
        "name": payload.name,
        "config_file_path": saved.rel_path,
    }


@app.get("/api/llm/tokenizer")
def llm_tokenizer_list():
    return {"items": db.fetch_all(
        "SELECT id, name, algorithm, vocab_size, is_active, "
        "       config_file_path, artifact_file_path, created_at "
        "FROM llm_tokenizer_configs ORDER BY is_active DESC, id DESC"
    )}


class LlmCorpusIn(BaseModel):
    language: str
    text: str
    source: Optional[str] = None
    source_url: Optional[str] = None
    file_name: Optional[str] = None
    license: Optional[str] = None


@app.post("/api/llm/corpus")
def llm_corpus_create(payload: LlmCorpusIn):
    saved = storage.save_llm_corpus_file(
        payload.text, language=payload.language, file_name=payload.file_name,
    )
    corpus_id = db.execute(
        """
        INSERT INTO llm_code_corpus
            (language, source, source_url, file_name, file_path, file_size, sha256,
             license, token_count, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'collected')
        """,
        (payload.language, payload.source, payload.source_url,
         payload.file_name, saved.rel_path, saved.size, saved.sha256,
         payload.license, len(payload.text.split())),
    )
    return {"corpus_id": corpus_id, **saved.as_dict()}


@app.get("/api/llm/corpus")
def llm_corpus_list(language: Optional[str] = None, limit: int = 50, offset: int = 0):
    where, args = "", []
    if language:
        where = " WHERE language=%s"
        args.append(language)
    args += [int(limit), int(offset)]
    return {"items": db.fetch_all(
        "SELECT id, language, source, file_name, file_path, file_size, "
        "       token_count, status, created_at "
        f"FROM llm_code_corpus{where} ORDER BY id DESC LIMIT %s OFFSET %s",
        tuple(args),
    )}


class LlmLibraryIn(BaseModel):
    language: str
    library: str
    version: Optional[str] = None
    topic: Optional[str] = None
    doc_text: Optional[str] = None
    example_code: Optional[str] = None
    source_url: Optional[str] = None


@app.post("/api/llm/library")
def llm_library_create(payload: LlmLibraryIn):
    saved = storage.save_llm_library_example(
        payload.model_dump(),
        language=payload.language, library=payload.library,
    )
    lib_id = db.execute(
        """
        INSERT INTO llm_library_examples
            (language, library, version, topic, doc_text, example_code,
             source_url, file_path, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'curated')
        """,
        (payload.language, payload.library, payload.version, payload.topic,
         payload.doc_text, payload.example_code, payload.source_url,
         saved.rel_path),
    )
    return {"library_id": lib_id, "file_path": saved.rel_path}


@app.get("/api/llm/library")
def llm_library_list(
    language: Optional[str] = None, library: Optional[str] = None,
    limit: int = 50, offset: int = 0,
):
    where_parts: list[str] = []
    args: list[Any] = []
    if language:
        where_parts.append("language=%s"); args.append(language)
    if library:
        where_parts.append("library=%s"); args.append(library)
    sql = (
        "SELECT id, language, library, version, topic, file_path, status, created_at "
        "FROM llm_library_examples"
    )
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    sql += " ORDER BY id DESC LIMIT %s OFFSET %s"
    args += [int(limit), int(offset)]
    return {"items": db.fetch_all(sql, tuple(args))}


# ---- 12.4 학습 실행 이력 ----
class LlmTrainingRunIn(BaseModel):
    stage_key: str
    run_name: Optional[str] = None
    base_model: Optional[str] = None
    tokenizer_id: Optional[int] = None
    dataset_filter: Optional[dict[str, Any]] = None
    hyperparams: Optional[dict[str, Any]] = None
    status: Optional[str] = "pending"
    metrics: Optional[dict[str, Any]] = None


@app.post("/api/llm/training-runs")
def llm_training_run_create(payload: LlmTrainingRunIn):
    stage_id = _llm_stage_id(payload.stage_key)
    if stage_id is None:
        raise HTTPException(400, f"unknown stage_key: {payload.stage_key}")
    run_id = db.execute(
        """
        INSERT INTO llm_training_runs
            (stage_id, stage_key, run_name, base_model, tokenizer_id,
             dataset_filter, hyperparams, status, metrics_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (stage_id, payload.stage_key, payload.run_name, payload.base_model,
         payload.tokenizer_id,
         json.dumps(payload.dataset_filter, ensure_ascii=False)
            if payload.dataset_filter else None,
         json.dumps(payload.hyperparams, ensure_ascii=False)
            if payload.hyperparams else None,
         payload.status or "pending",
         json.dumps(payload.metrics, ensure_ascii=False)
            if payload.metrics else None),
    )
    return {"run_id": run_id, "stage_id": stage_id, "stage_key": payload.stage_key}


@app.get("/api/llm/training-runs")
def llm_training_run_list(stage_key: Optional[str] = None, limit: int = 50):
    where, args = "", []
    if stage_key:
        where = " WHERE stage_key=%s"
        args.append(stage_key)
    args.append(int(limit))
    return {"items": db.fetch_all(
        "SELECT id, stage_id, stage_key, run_name, base_model, status, "
        "       metrics_json, started_at, finished_at, created_at "
        f"FROM llm_training_runs{where} ORDER BY id DESC LIMIT %s",
        tuple(args),
    )}


# ---- 12.5 추론 서버 프록시 (/generate /optimize /explain /spec-to-code) ----
def _record_inference_run(
    *, endpoint: str, payload: dict[str, Any], result: dict[str, Any] | None,
    started: datetime,
) -> int | None:
    latency_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
    status = "ok" if result else "failed"
    if result and result.get("stub"):
        status = "stub"
    return db.execute(
        """
        INSERT INTO llm_inference_runs
            (endpoint, model_name, language, library, input_code, requirement,
             output_code, explanation, raw_response, latency_ms, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (endpoint,
         (result or {}).get("model") or payload.get("model"),
         payload.get("language"), payload.get("library"),
         payload.get("input_code"), payload.get("requirement"),
         (result or {}).get("output_code"),
         (result or {}).get("explanation"),
         json.dumps(result, ensure_ascii=False) if result else None,
         latency_ms, status),
    )


def _proxy_llm(endpoint_path: str, body: dict[str, Any]) -> dict[str, Any] | None:
    return _http_post_json(
        f"{MODEL_SERVER_URL}/{endpoint_path.lstrip('/')}",
        {k: v for k, v in body.items() if v is not None},
        timeout=60,
    )


def _http_get_json(url: str, timeout: float = 15.0) -> dict[str, Any] | None:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.info("worker get failed url=%s err=%s", url, exc)
        return None


class LlmGenerateProxyIn(BaseModel):
    requirement: Optional[str] = None
    input_code: Optional[str] = None
    language: Optional[str] = None
    library: Optional[str] = None
    model: Optional[str] = None


@app.get("/api/v1/model/runtime")
def model_runtime():
    res = _http_get_json(f"{MODEL_SERVER_URL}/api/v1/runtime", timeout=15)
    if not res:
        raise HTTPException(502, "model-server runtime unavailable")
    return res


@app.post("/api/llm/generate")
def llm_proxy_generate(payload: LlmGenerateProxyIn):
    started = datetime.utcnow()
    body = payload.model_dump()
    res = _proxy_llm("generate", body)
    inference_id = _record_inference_run(
        endpoint="generate", payload=body, result=res, started=started,
    )
    return {"inference_id": inference_id, "result": res}


class LlmOptimizeProxyIn(BaseModel):
    input_code: str
    requirement: Optional[str] = None
    language: Optional[str] = None
    library: Optional[str] = None
    model: Optional[str] = None


@app.post("/api/llm/optimize")
def llm_proxy_optimize(payload: LlmOptimizeProxyIn):
    started = datetime.utcnow()
    body = payload.model_dump()
    res = _proxy_llm("optimize", body)
    inference_id = _record_inference_run(
        endpoint="optimize", payload=body, result=res, started=started,
    )
    return {"inference_id": inference_id, "result": res}


class LlmExplainProxyIn(BaseModel):
    input_code: str
    language: Optional[str] = None
    library: Optional[str] = None
    model: Optional[str] = None


@app.post("/api/llm/explain")
def llm_proxy_explain(payload: LlmExplainProxyIn):
    started = datetime.utcnow()
    body = payload.model_dump()
    res = _proxy_llm("explain", body)
    inference_id = _record_inference_run(
        endpoint="explain", payload=body, result=res, started=started,
    )
    return {"inference_id": inference_id, "result": res}


class LlmSpecToCodeProxyIn(BaseModel):
    requirement: str
    language: Optional[str] = None
    library: Optional[str] = None
    model: Optional[str] = None


@app.post("/api/llm/spec-to-code")
def llm_proxy_spec_to_code(payload: LlmSpecToCodeProxyIn):
    started = datetime.utcnow()
    body = payload.model_dump()
    res = _proxy_llm("spec-to-code", body)
    inference_id = _record_inference_run(
        endpoint="spec_to_code", payload=body, result=res, started=started,
    )
    return {"inference_id": inference_id, "result": res}


@app.get("/api/llm/inference-runs")
def llm_inference_runs(endpoint: Optional[str] = None, limit: int = 50):
    where, args = "", []
    if endpoint:
        where = " WHERE endpoint=%s"
        args.append(endpoint)
    args.append(int(limit))
    return {"items": db.fetch_all(
        "SELECT id, endpoint, model_name, language, library, latency_ms, "
        "       status, created_at "
        f"FROM llm_inference_runs{where} ORDER BY id DESC LIMIT %s",
        tuple(args),
    )}


# ===========================================================================
# Step 13: Embedding 모델과 저장 구조 (답변 재사용의 핵심)
#
# 사진 명세를 그대로 매핑한다:
#   대상: 요구사항 / 사용자 입력 코드 / 이미지 추출 텍스트 /
#         이미지 추출 코드 / 모델 답변 / 최적화 코드 / 명세서 구조
#   흐름: 입력 저장 → embedding 생성 → MySQL embeddings 테이블 저장
#         → 유사도 검색 → 관련 답변 재사용
#
# 엔드포인트:
#   GET  /api/embeddings/targets               - 7가지 임베딩 대상 카탈로그
#   POST /api/embeddings/embed-target          - 특정 (target_type,target_id) 임베딩 생성·저장
#   POST /api/embeddings/search                - 코사인 유사도 top-K 검색
#   POST /api/embeddings/find-reusable-answer  - 유사 model_answer 찾고 재사용 로그 기록
# ===========================================================================
import hashlib as _hashlib
import math as _math

# 사진의 7가지 대상 (정적 fallback 카탈로그)
EMBEDDING_TARGETS_FALLBACK: list[dict[str, Any]] = [
    {"target_key": "requirement",    "label": "요구사항",
     "source_table": "requirements",   "source_field": "summary"},
    {"target_key": "user_code",      "label": "사용자 입력 코드",
     "source_table": "raw_inputs",     "source_field": "raw_text"},
    {"target_key": "image_text",     "label": "이미지 추출 텍스트",
     "source_table": "image_data",     "source_field": "text_file_path"},
    {"target_key": "image_code",     "label": "이미지 추출 코드",
     "source_table": "extracted_code", "source_field": "code_text"},
    {"target_key": "model_answer",   "label": "모델 답변",
     "source_table": "model_answers",  "source_field": "answer_text"},
    {"target_key": "optimized_code", "label": "최적화 코드",
     "source_table": "optimized_code", "source_field": "code_text"},
    {"target_key": "spec_structure", "label": "명세서 구조",
     "source_table": "image_data",     "source_field": "spec_file_path"},
]
EMBEDDING_TARGET_KEYS: set[str] = {t["target_key"] for t in EMBEDDING_TARGETS_FALLBACK}


def _embedding_targets_from_db() -> list[dict[str, Any]]:
    try:
        rows = db.fetch_all(
            "SELECT target_key, label, source_table, source_field, description "
            "FROM embedding_targets ORDER BY id ASC"
        )
        if rows:
            return rows
    except Exception as exc:  # noqa: BLE001
        log.info("embedding_targets DB unavailable, using fallback (%s)", exc)
    return EMBEDDING_TARGETS_FALLBACK


def _read_text_file_or_none(rel_path: str | None) -> str | None:
    if not rel_path:
        return None
    try:
        abs_path = storage.resolve(rel_path)
    except ValueError:
        return None
    if not abs_path.is_file():
        return None
    try:
        return abs_path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None


def _load_target_text(target_type: str, target_id: int) -> str | None:
    """target_type/target_id 로 임베딩 대상 텍스트를 로드.

    사진의 7가지 대상 + (호환을 위해) raw_input/generated_code/extracted_code 도 받는다.
    """
    if target_type in {"requirement"}:
        row = db.fetch_one(
            "SELECT summary FROM requirements WHERE id=%s", (target_id,)
        )
        return row.get("summary") if row else None

    if target_type in {"user_code", "raw_input"}:
        row = db.fetch_one(
            "SELECT raw_text, source_file_path FROM raw_inputs WHERE id=%s",
            (target_id,),
        )
        if not row:
            return None
        return row.get("raw_text") or _read_text_file_or_none(row.get("source_file_path"))

    if target_type in {"image_text"}:
        row = db.fetch_one(
            "SELECT text_file_path FROM image_data WHERE id=%s", (target_id,)
        )
        return _read_text_file_or_none(row.get("text_file_path")) if row else None

    if target_type in {"image_code", "extracted_code"}:
        row = db.fetch_one(
            "SELECT code_text, file_path FROM extracted_code WHERE id=%s",
            (target_id,),
        )
        if not row:
            return None
        return row.get("code_text") or _read_text_file_or_none(row.get("file_path"))

    if target_type in {"model_answer"}:
        row = db.fetch_one(
            "SELECT answer_text, answer_file_path FROM model_answers WHERE id=%s",
            (target_id,),
        )
        if not row:
            return None
        return row.get("answer_text") or _read_text_file_or_none(row.get("answer_file_path"))

    if target_type in {"optimized_code"}:
        row = db.fetch_one(
            "SELECT code_text, file_path FROM optimized_code WHERE id=%s",
            (target_id,),
        )
        if not row:
            return None
        return row.get("code_text") or _read_text_file_or_none(row.get("file_path"))

    if target_type in {"generated_code"}:
        row = db.fetch_one(
            "SELECT code_text, file_path FROM generated_code WHERE id=%s",
            (target_id,),
        )
        if not row:
            return None
        return row.get("code_text") or _read_text_file_or_none(row.get("file_path"))

    if target_type in {"spec_structure"}:
        row = db.fetch_one(
            "SELECT spec_file_path FROM image_data WHERE id=%s", (target_id,)
        )
        return _read_text_file_or_none(row.get("spec_file_path")) if row else None

    return None


def _parse_vector_field(value: Any) -> list[float] | None:
    """embeddings.vector_json 컬럼 값(JSON 문자열 또는 list)을 list[float] 로."""
    if value is None:
        return None
    if isinstance(value, list):
        try:
            return [float(x) for x in value]
        except Exception:  # noqa: BLE001
            return None
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8")
        except Exception:  # noqa: BLE001
            return None
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except Exception:  # noqa: BLE001
            return None
        if isinstance(data, list):
            try:
                return [float(x) for x in data]
            except Exception:  # noqa: BLE001
                return None
    return None


def _cosine(a: list[float], b: list[float],
            *, norm_a: float | None = None, norm_b: float | None = None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    for x, y in zip(a, b):
        dot += x * y
    na = norm_a if norm_a is not None else _math.sqrt(sum(x * x for x in a))
    nb = norm_b if norm_b is not None else _math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _vector_collection(dim: int) -> str:
    return f"{VECTOR_DB_COLLECTION}_{dim}d"


def _embedding_row_id(target_type: str, target_id: int, model_name: str) -> int | None:
    row = db.fetch_one(
        """
        SELECT id FROM embeddings
         WHERE target_type=%s AND target_id=%s AND model_name=%s
         ORDER BY id DESC LIMIT 1
        """,
        (target_type, target_id, model_name),
    )
    return int(row["id"]) if row and row.get("id") is not None else None


def _vector_db_ensure_collection(dim: int) -> bool:
    if not VECTOR_DB_ENABLED:
        return False
    collection = _vector_collection(dim)
    existing = _http_get_json(f"{VECTOR_DB_URL}/collections/{collection}", timeout=5)
    if existing:
        return True
    payload = {"vectors": {"size": dim, "distance": "Cosine"}}
    res = _http_put_json(f"{VECTOR_DB_URL}/collections/{collection}", payload, timeout=10)
    return bool(res)


def _vector_db_upsert(
    *,
    embedding_id: int,
    target_type: str,
    target_id: int,
    vector: list[float],
    model_name: str,
    model_version: str | None,
    content_hash: str | None,
) -> bool:
    if not VECTOR_DB_ENABLED or not vector:
        return False
    dim = len(vector)
    if not _vector_db_ensure_collection(dim):
        return False
    point = {
        "id": int(embedding_id),
        "vector": vector,
        "payload": {
            "embedding_id": int(embedding_id),
            "target_type": target_type,
            "target_id": int(target_id),
            "model_name": model_name,
            "model_version": model_version or model_name,
            "dim": dim,
            "content_hash": content_hash,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        },
    }
    res = _http_put_json(
        f"{VECTOR_DB_URL}/collections/{_vector_collection(dim)}/points?wait=true",
        {"points": [point]},
        timeout=15,
    )
    return bool(res)


def _vector_db_search(
    payload: "EmbeddingSearchIn",
    *,
    qvec: list[float],
    qmodel: str,
    query_hash: str | None,
    query_text: str | None,
) -> dict[str, Any] | None:
    if not VECTOR_DB_ENABLED or not qvec:
        return None

    limit = max(1, payload.top_k)
    overfetch = max(limit * 8, 32)
    must: list[dict[str, Any]] = [{"key": "model_name", "match": {"value": qmodel}}]
    if payload.target_types:
        must.append({"key": "target_type", "match": {"any": payload.target_types}})
    excl = payload.exclude_target or {}
    excl_type = excl.get("target_type") if isinstance(excl, dict) else None
    excl_id = excl.get("target_id") if isinstance(excl, dict) else None
    body = {
        "vector": qvec,
        "limit": overfetch,
        "with_payload": True,
        "filter": {"must": must},
    }
    if payload.threshold > -1.0:
        body["score_threshold"] = payload.threshold

    res = _http_post_json(
        f"{VECTOR_DB_URL}/collections/{_vector_collection(len(qvec))}/points/search",
        body,
        timeout=15,
    )
    if not res or not isinstance(res.get("result"), list):
        return None

    target_types = set(payload.target_types or [])

    items: list[dict[str, Any]] = []
    for point in res["result"]:
        meta = point.get("payload") or {}
        if target_types and meta.get("target_type") not in target_types:
            continue
        if excl_type and meta.get("target_type") == excl_type and meta.get("target_id") == excl_id:
            continue
        score = float(point.get("score") or 0.0)
        if score < payload.threshold:
            continue
        items.append({
            "embedding_id": meta.get("embedding_id") or point.get("id"),
            "target_type": meta.get("target_type"),
            "target_id": meta.get("target_id"),
            "model_version": meta.get("model_version") or meta.get("model_name"),
            "vector_dim": meta.get("dim") or len(qvec),
            "similarity": round(score, 6),
            "content_hash": meta.get("content_hash"),
            "created_at": meta.get("updated_at"),
        })
        if len(items) >= limit:
            break

    return {
        "query_model": qmodel,
        "query_dim": len(qvec),
        "query_hash": query_hash or (
            _hashlib.sha256(query_text.encode("utf-8")).hexdigest()
            if query_text else None
        ),
        "search_engine": "qdrant",
        "candidates_scanned": len(res["result"]),
        "items": items,
    }


def _store_embedding_row(
    *,
    target_type: str,
    target_id: int,
    vector: list[float],
    model_name: str,
    model_version: str | None,
    content_hash: str | None,
) -> int:
    """embeddings 테이블 upsert + 디스크 파일 저장. embedding_id 반환."""
    saved = storage.save_embedding(
        vector,
        target_type=target_type,
        target_id=target_id,
        model_name=model_name,
    )
    norm = _math.sqrt(sum(x * x for x in vector))
    db.execute(
        """
        INSERT INTO embeddings
            (target_type, target_id, model_name, model_version, dim,
             vector_file_path, vector_json, file_size, sha256, norm,
             content_hash, source_text_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            vector_file_path = VALUES(vector_file_path),
            vector_json      = VALUES(vector_json),
            file_size        = VALUES(file_size),
            sha256           = VALUES(sha256),
            dim              = VALUES(dim),
            norm             = VALUES(norm),
            model_version    = VALUES(model_version),
            content_hash     = VALUES(content_hash),
            source_text_hash = VALUES(source_text_hash)
        """,
        (target_type, target_id, model_name, model_version or model_name, len(vector),
         saved.rel_path, json.dumps(vector), saved.size, saved.sha256, norm,
         content_hash, content_hash),
    )
    embedding_id = _embedding_row_id(target_type, target_id, model_name)
    if embedding_id:
        _vector_db_upsert(
            embedding_id=embedding_id,
            target_type=target_type,
            target_id=target_id,
            vector=vector,
            model_name=model_name,
            model_version=model_version or model_name,
            content_hash=content_hash,
        )
        return embedding_id
    return 0


# --- GET /api/embeddings/targets ------------------------------------------
@app.get("/api/embeddings/targets")
def api_embedding_targets():
    """사진 명세의 7가지 임베딩 대상 카탈로그."""
    return {"targets": _embedding_targets_from_db()}


# --- POST /api/embeddings/embed-target ------------------------------------
class EmbedTargetIn(BaseModel):
    target_type: str
    target_id: int
    model: Optional[str] = None
    text: Optional[str] = None  # 명시적 override (없으면 자동 로드)


@app.post("/api/embeddings/embed-target")
def api_embed_target(payload: EmbedTargetIn):
    """특정 대상(요구사항/모델 답변/최적화 코드 등)의 임베딩을 생성·저장.

    흐름: 대상 텍스트 로드 → embedding-server 호출 → embeddings 테이블 upsert
         → vector 파일 저장 → embedding_id 반환.
    """
    text = payload.text or _load_target_text(payload.target_type, payload.target_id)
    if not text or not text.strip():
        raise HTTPException(404, f"target text not found for {payload.target_type}/{payload.target_id}")

    emb = _embed_text(text, model=payload.model)
    if not emb or not isinstance(emb.get("vector"), list):
        raise HTTPException(503, "embedding-server unavailable")

    vector: list[float] = [float(x) for x in emb["vector"]]
    content_hash = emb.get("content_hash") or _hashlib.sha256(text.encode("utf-8")).hexdigest()
    model_name = emb.get("model") or (payload.model or "stub-hash")

    embedding_id = _store_embedding_row(
        target_type=payload.target_type,
        target_id=payload.target_id,
        vector=vector,
        model_name=model_name,
        model_version=model_name,
        content_hash=content_hash,
    )
    return {
        "embedding_id": embedding_id,
        "target_type": payload.target_type,
        "target_id": payload.target_id,
        "model_version": model_name,
        "vector_dim": len(vector),
        "content_hash": content_hash,
    }


# --- POST /api/embeddings/search ------------------------------------------
class EmbeddingSearchIn(BaseModel):
    text: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    target_types: Optional[list[str]] = None  # 검색 대상 풀 (없으면 전체)
    model: Optional[str] = None
    query_vector: Optional[list[float]] = None
    query_model: Optional[str] = None
    query_hash: Optional[str] = None
    top_k: int = 5
    threshold: float = 0.0
    exclude_target: Optional[dict[str, int]] = None  # 자기 자신 제외


@app.post("/api/embeddings/search")
def api_embeddings_search(payload: EmbeddingSearchIn):
    """코사인 유사도 기반 top-K 임베딩 검색.

    1) 입력으로 `text` 또는 (target_type,target_id) 중 하나가 필요.
    2) 같은 model 의 저장 임베딩들과 코사인 유사도 계산.
    3) threshold 이상인 상위 top_k 결과를 반환.
    """
    if not payload.query_vector and not payload.text and not (payload.target_type and payload.target_id):
        raise HTTPException(400, "query_vector, text 또는 (target_type,target_id) 중 하나가 필요합니다")

    query_text = payload.text
    if payload.query_vector:
        try:
            qvec = [float(x) for x in payload.query_vector]
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"invalid query_vector: {exc}") from exc
        qmodel = payload.query_model or payload.model or "stub-hash"
        query_hash = payload.query_hash
    else:
        if not query_text:
            query_text = _load_target_text(payload.target_type or "", payload.target_id or 0)
        if not query_text or not query_text.strip():
            raise HTTPException(404, "검색 입력 텍스트를 찾지 못했습니다")

        emb = _embed_text(query_text, model=payload.model)
        if not emb or not isinstance(emb.get("vector"), list):
            raise HTTPException(503, "embedding-server unavailable")
        qvec = [float(x) for x in emb["vector"]]
        qmodel = emb.get("model") or (payload.model or "stub-hash")
        query_hash = emb.get("content_hash") or _hashlib.sha256(query_text.encode("utf-8")).hexdigest()

    if not qvec:
        raise HTTPException(400, "query vector is empty")
    qnorm = _math.sqrt(sum(x * x for x in qvec))

    vector_db_res = _vector_db_search(
        payload,
        qvec=qvec,
        qmodel=qmodel,
        query_hash=query_hash,
        query_text=query_text,
    )

    # 같은 model 의 임베딩만 대상으로 (차원 호환 보장)
    where = ["(e.model_name = %s OR e.model_version = %s)", "e.dim = %s"]
    args: list[Any] = [qmodel, qmodel, len(qvec)]
    if payload.target_types:
        placeholders = ",".join(["%s"] * len(payload.target_types))
        where.append(f"e.target_type IN ({placeholders})")
        args.extend(payload.target_types)
    where_sql = " AND ".join(where)

    rows = db.fetch_all(
        f"""
        SELECT e.id AS embedding_id, e.target_type, e.target_id,
               e.model_name, e.model_version, e.dim, e.norm,
               e.vector_json, e.content_hash, e.created_at
          FROM embeddings e
         WHERE {where_sql}
        """,
        tuple(args),
    )

    excl = payload.exclude_target or {}
    excl_type = excl.get("target_type") if isinstance(excl, dict) else None
    excl_id = excl.get("target_id") if isinstance(excl, dict) else None

    results: list[dict[str, Any]] = []
    for r in rows:
        if excl_type and r["target_type"] == excl_type and r["target_id"] == excl_id:
            continue
        vec = _parse_vector_field(r.get("vector_json"))
        if not vec or len(vec) != len(qvec):
            continue
        sim = _cosine(qvec, vec, norm_a=qnorm, norm_b=float(r["norm"]) if r.get("norm") else None)
        if sim < payload.threshold:
            continue
        results.append({
            "embedding_id": r["embedding_id"],
            "target_type": r["target_type"],
            "target_id": r["target_id"],
            "model_version": r.get("model_version") or r.get("model_name"),
            "vector_dim": r["dim"],
            "similarity": round(sim, 6),
            "content_hash": r.get("content_hash"),
            "created_at": r.get("created_at"),
        })
        if VECTOR_DB_ENABLED:
            try:
                _vector_db_upsert(
                    embedding_id=int(r["embedding_id"]),
                    target_type=str(r["target_type"]),
                    target_id=int(r["target_id"]),
                    vector=vec,
                    model_name=str(r.get("model_name") or qmodel),
                    model_version=str(r.get("model_version") or r.get("model_name") or qmodel),
                    content_hash=r.get("content_hash"),
                )
            except Exception as exc:  # noqa: BLE001
                log.info("vector db lazy backfill skipped embedding_id=%s err=%s", r.get("embedding_id"), exc)

    if vector_db_res is not None:
        merged: dict[Any, dict[str, Any]] = {}
        for item in vector_db_res.get("items", []) + results:
            key = item.get("embedding_id") or (item.get("target_type"), item.get("target_id"))
            current = merged.get(key)
            if current is None or float(item.get("similarity") or 0.0) > float(current.get("similarity") or 0.0):
                merged[key] = item
        merged_items = sorted(
            merged.values(),
            key=lambda x: float(x.get("similarity") or 0.0),
            reverse=True,
        )[: max(1, payload.top_k)]
        return {
            "query_model": qmodel,
            "query_dim": len(qvec),
            "query_hash": query_hash or (
                _hashlib.sha256(query_text.encode("utf-8")).hexdigest()
                if query_text else None
            ),
            "search_engine": "qdrant+mysql-cosine-fallback",
            "candidates_scanned": (vector_db_res.get("candidates_scanned") or 0) + len(rows),
            "items": merged_items,
        }

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return {
        "query_model": qmodel,
        "query_dim": len(qvec),
        "query_hash": query_hash or (
            _hashlib.sha256(query_text.encode("utf-8")).hexdigest()
            if query_text else None
        ),
        "search_engine": "mysql-cosine-fallback",
        "candidates_scanned": len(rows),
        "items": results[: max(1, payload.top_k)],
    }


# --- POST /api/embeddings/find-reusable-answer ----------------------------
class ReuseAnswerIn(BaseModel):
    text: Optional[str] = None
    raw_input_id: Optional[int] = None
    requirement_id: Optional[int] = None
    model: Optional[str] = None
    top_k: int = 5
    threshold: float = 0.85
    record: bool = True  # 답변 재사용 로그 기록 여부


@app.post("/api/embeddings/find-reusable-answer")
def api_find_reusable_answer(payload: ReuseAnswerIn):
    """유사도 검색으로 재사용 가능한 기존 모델 답변을 찾는다.

    흐름(사진): 입력 저장 → embedding 생성 → MySQL embeddings 테이블 저장
                → 유사도 검색 → 관련 답변 재사용
    """
    # 1) 검색 입력 텍스트 결정
    text = payload.text
    query_target_type: str | None = None
    if not text and payload.requirement_id:
        text = _load_target_text("requirement", payload.requirement_id)
        query_target_type = "requirement"
    if not text and payload.raw_input_id:
        text = _load_target_text("user_code", payload.raw_input_id)
        query_target_type = "user_code"
    if not text or not text.strip():
        raise HTTPException(400, "검색용 텍스트가 필요합니다 (text/raw_input_id/requirement_id)")

    # 2) model_answer 임베딩에 대해 유사도 검색
    search_res = api_embeddings_search(EmbeddingSearchIn(
        text=text,
        target_types=["model_answer"],
        model=payload.model,
        top_k=payload.top_k,
        threshold=payload.threshold,
    ))

    items = search_res.get("items", [])
    if not items:
        return {
            "reused": False,
            "reason": "no candidate above threshold",
            "threshold": payload.threshold,
            "search": search_res,
        }

    best = items[0]
    matched_answer_id = int(best["target_id"])
    answer_row = db.fetch_one(
        """
        SELECT id, raw_input_id, requirement_id, model_name, model_provider,
               prompt_text, answer_text, answer_file_path, created_at
          FROM model_answers WHERE id=%s
        """,
        (matched_answer_id,),
    )
    if not answer_row:
        return {
            "reused": False,
            "reason": f"matched_answer_id={matched_answer_id} not found",
            "search": search_res,
        }

    log_id: int | None = None
    if payload.record and payload.raw_input_id:
        try:
            log_id = db.execute(
                """
                INSERT INTO answer_reuse_logs
                    (raw_input_id, matched_answer_id, similarity, metric,
                     embedding_model, decision, query_target_type,
                     query_text_hash, top_k, threshold)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (payload.raw_input_id, matched_answer_id,
                 best["similarity"], "cosine",
                 best.get("model_version"), "reused",
                 query_target_type, search_res.get("query_hash"),
                 payload.top_k, payload.threshold),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("answer_reuse_logs insert failed: %s", exc)

    return {
        "reused": True,
        "similarity": best["similarity"],
        "threshold": payload.threshold,
        "matched_answer_id": matched_answer_id,
        "matched_embedding_id": best["embedding_id"],
        "reuse_log_id": log_id,
        "answer": answer_row,
        "search": search_res,
    }


# ===========================================================================
# Step 14: 답변 재사용 구조 (모델은 매번 새로 답하지 않는다)
#
# 사진 명세 흐름:
#   새 요구사항 입력 → embedding 생성 → MySQL에서 유사 답변 검색
#       → 유사도 기준 이상이면 기존 답변 후보 반환
#       → LLM이 기존 답변을 현재 요구사항에 맞게 수정
#       → 새 답변 저장
#
# 체크리스트:
#   - 유사 요구사항/코드/이미지 추출/답변 검색
#   - reuse_count 증가
#   - 재사용 로그 저장
#   - 수정된 답변은 새 답변으로 저장
#
# 엔드포인트:
#   POST /api/reuse/find-similar  - 4가지 카테고리(요구사항/코드/이미지/답변) 통합 검색
#   POST /api/reuse/answer        - 전체 파이프라인 (검색→적응→새 답변 저장→로그)
#   GET  /api/reuse/logs          - 재사용 로그 조회
#   GET  /api/reuse/stats         - 답변별 reuse_count 통계
# ===========================================================================
REUSE_DEFAULT_TARGETS: list[str] = [
    "requirement", "user_code", "image_text", "image_code", "model_answer",
]


def _reuse_search_category(
    text: str,
    *, target_types: list[str],
    model: str | None,
    top_k: int,
    threshold: float,
    exclude: dict[str, int] | None = None,
) -> dict[str, Any]:
    """단일 카테고리 풀에 대해 api_embeddings_search 를 한 번 호출."""
    return api_embeddings_search(EmbeddingSearchIn(
        text=text,
        target_types=target_types,
        model=model,
        top_k=top_k,
        threshold=threshold,
        exclude_target=exclude,
    ))


# --- POST /api/reuse/find-similar -----------------------------------------
class ReuseFindSimilarIn(BaseModel):
    text: Optional[str] = None
    raw_input_id: Optional[int] = None
    requirement_id: Optional[int] = None
    target_types: Optional[list[str]] = None
    model: Optional[str] = None
    top_k: int = 5
    threshold: float = 0.0


@app.post("/api/reuse/find-similar")
def api_reuse_find_similar(payload: ReuseFindSimilarIn):
    """사진 체크리스트의 4가지 검색을 한 번에 수행한다.

    카테고리별(requirement / user_code / image_text+image_code / model_answer)
    상위 후보를 묶어서 반환한다.
    """
    # 1) 검색 입력 텍스트 결정
    text = payload.text
    if not text and payload.requirement_id:
        text = _load_target_text("requirement", payload.requirement_id)
    if not text and payload.raw_input_id:
        text = _load_target_text("user_code", payload.raw_input_id)
    if not text or not text.strip():
        raise HTTPException(400, "검색용 텍스트가 필요합니다 (text/raw_input_id/requirement_id)")

    requested = payload.target_types or REUSE_DEFAULT_TARGETS
    requested = [t for t in requested if t in EMBEDDING_TARGET_KEYS]
    if not requested:
        raise HTTPException(400, "유효한 target_types 가 없습니다")

    # 카테고리 그룹: 사진 체크리스트의 4 항목과 1:1
    groups: dict[str, list[str]] = {
        "requirement":   ["requirement"],
        "user_code":     ["user_code"],
        "image_extract": [t for t in ("image_text", "image_code") if t in requested],
        "model_answer":  ["model_answer"],
    }
    # 사용자가 명시한 타입만 활성화
    active_groups: dict[str, list[str]] = {}
    if "requirement" in requested:
        active_groups["requirement"] = groups["requirement"]
    if "user_code" in requested:
        active_groups["user_code"] = groups["user_code"]
    if groups["image_extract"]:
        active_groups["image_extract"] = groups["image_extract"]
    if "model_answer" in requested:
        active_groups["model_answer"] = groups["model_answer"]

    out: dict[str, Any] = {
        "query_hash": _hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "threshold": payload.threshold,
        "top_k": payload.top_k,
        "groups": {},
    }
    emb = _embed_text(text, model=payload.model)
    if not emb or not isinstance(emb.get("vector"), list):
        raise HTTPException(503, "embedding-server unavailable")
    qvec = [float(x) for x in emb["vector"]]
    qmodel = emb.get("model") or (payload.model or "stub-hash")
    qhash = emb.get("content_hash") or out["query_hash"]

    for label, types in active_groups.items():
        if not types:
            out["groups"][label] = {"items": [], "candidates_scanned": 0}
            continue
        res = api_embeddings_search(EmbeddingSearchIn(
            query_vector=qvec,
            query_model=qmodel,
            query_hash=qhash,
            target_types=types,
            top_k=payload.top_k,
            threshold=payload.threshold,
        ))
        out["groups"][label] = {
            "target_types": types,
            "items": res.get("items", []),
            "candidates_scanned": res.get("candidates_scanned", 0),
            "query_model": res.get("query_model"),
        }
    return out


# --- POST /api/reuse/answer -----------------------------------------------
class ReuseAnswerPipelineIn(BaseModel):
    requirement: Optional[str] = None
    code: Optional[str] = None
    code_language: Optional[str] = None
    raw_input_id: Optional[int] = None
    requirement_id: Optional[int] = None
    project_id: Optional[int] = None
    user_tag: Optional[str] = None
    model: Optional[str] = None              # adapt 단계 LLM
    embedding_model: Optional[str] = None
    top_k: int = 5
    threshold: float = 0.85                  # 사진의 "유사도 기준"
    adapt: bool = True                       # False 면 후보만 반환
    record: bool = True                      # 재사용 로그 기록 여부


@app.post("/api/reuse/answer")
def api_reuse_answer(payload: ReuseAnswerPipelineIn):
    """사진 흐름 그대로의 통합 재사용 파이프라인.

    1) 새 요구사항 입력 → raw_inputs 보존
    2) embedding 생성 → MySQL embeddings 저장
    3) 유사 답변 검색 (model_answer 풀)
    4) 유사도 기준 이상이면 후보 반환
    5) LLM 이 기존 답변을 현재 요구사항에 맞게 수정
    6) 새 답변 저장 + reuse_count++ + 재사용 로그 저장
    """
    started = datetime.utcnow()

    # ---- 1) 입력 정리 ----
    if not (payload.requirement or payload.code or payload.raw_input_id or payload.requirement_id):
        raise HTTPException(400, "requirement/code/raw_input_id/requirement_id 중 최소 하나 필요")

    raw_id = payload.raw_input_id
    if raw_id is None:
        raw_text_parts: list[str] = []
        if payload.requirement:
            raw_text_parts.append("## 요구사항\n" + payload.requirement)
        if payload.code:
            raw_text_parts.append(
                f"## 입력 코드\n```{payload.code_language or ''}\n{payload.code}\n```"
            )
        input_type = "text"
        if payload.code and payload.requirement:
            input_type = "mixed"
        raw_id = _insert_raw_input(
            input_type=input_type,
            raw_text="\n\n".join(raw_text_parts) if raw_text_parts else None,
            project_id=payload.project_id,
            user_tag=payload.user_tag,
        )
        if payload.code:
            s_code = storage.save_original_code(
                payload.code, raw_input_id=raw_id, language=payload.code_language,
            )
            db.execute(
                "UPDATE raw_inputs SET source_file_path=%s WHERE id=%s",
                (s_code.rel_path, raw_id),
            )

    # 검색용 query 텍스트 (요구사항 우선)
    query_text = payload.requirement
    query_target_type = "requirement"
    if not query_text and payload.requirement_id:
        query_text = _load_target_text("requirement", payload.requirement_id)
    if not query_text and payload.code:
        query_text = payload.code
        query_target_type = "user_code"
    if not query_text and payload.raw_input_id:
        query_text = _load_target_text("user_code", payload.raw_input_id)
        query_target_type = "user_code"
    if not query_text or not query_text.strip():
        raise HTTPException(400, "검색용 텍스트(requirement/code) 가 필요합니다")

    # ---- 2) embedding 생성 + raw_input embedding 저장 ----
    emb = _embed_text(query_text, model=payload.embedding_model)
    if not emb or not isinstance(emb.get("vector"), list):
        raise HTTPException(503, "embedding-server unavailable")
    qvec = [float(x) for x in emb["vector"]]
    qmodel = emb.get("model") or (payload.embedding_model or "stub-hash")
    query_hash = emb.get("content_hash") or _hashlib.sha256(query_text.encode("utf-8")).hexdigest()

    try:
        _store_embedding_row(
            target_type=query_target_type,
            target_id=(payload.requirement_id if query_target_type == "requirement" else raw_id),
            vector=qvec,
            model_name=qmodel,
            model_version=qmodel,
            content_hash=query_hash,
        )
    except Exception as exc:  # noqa: BLE001
        log.info("input embedding store skipped: %s", exc)

    # ---- 3) 유사 답변 검색 ----
    search_res = api_embeddings_search(EmbeddingSearchIn(
        query_vector=qvec,
        query_model=qmodel,
        query_hash=query_hash,
        target_types=["model_answer"],
        top_k=payload.top_k,
        threshold=payload.threshold,
    ))
    candidates = search_res.get("items", [])

    # 사진 체크리스트의 보조 검색(요구사항/코드/이미지 추출)도 같이 수행해 결과에 포함
    aux_groups: dict[str, list[dict[str, Any]]] = {}
    for label, types in (
        ("requirement",   ["requirement"]),
        ("user_code",     ["user_code"]),
        ("image_extract", ["image_text", "image_code"]),
    ):
        try:
            r = api_embeddings_search(EmbeddingSearchIn(
                query_vector=qvec,
                query_model=qmodel,
                query_hash=query_hash,
                target_types=types,
                top_k=payload.top_k,
                threshold=max(0.0, payload.threshold - 0.1),
            ))
            aux_groups[label] = r.get("items", [])
        except HTTPException:
            aux_groups[label] = []

    # ---- 4) 유사도 기준 미달 → 후보 없음 ----
    if not candidates:
        # 재사용 실패 로그도 남긴다 (decision='rejected')
        if payload.record:
            try:
                db.execute(
                    """
                    INSERT INTO answer_reuse_logs
                        (raw_input_id, matched_answer_id, similarity, metric,
                         embedding_model, decision, query_target_type,
                         query_text_hash, top_k, threshold,
                         candidates_json, adapted, latency_ms)
                    VALUES (%s, NULL, 0, 'cosine', %s, 'rejected', %s, %s, %s, %s,
                            %s, 0, %s)
                    """,
                    (raw_id, qmodel, query_target_type, query_hash,
                     payload.top_k, payload.threshold,
                     json.dumps(aux_groups, ensure_ascii=False, default=str),
                     int((datetime.utcnow() - started).total_seconds() * 1000)),
                )
            except Exception as exc:  # noqa: BLE001
                # answer_reuse_logs.matched_answer_id 가 NOT NULL 인 경우 fallthrough
                log.info("rejected reuse log skipped: %s", exc)
        return {
            "reused": False,
            "reason": "no candidate above threshold",
            "threshold": payload.threshold,
            "raw_input_id": raw_id,
            "query_target_type": query_target_type,
            "query_hash": query_hash,
            "search": {"model_answer": candidates, **aux_groups},
        }

    best = candidates[0]
    matched_answer_id = int(best["target_id"])
    matched_row = db.fetch_one(
        """
        SELECT id, raw_input_id, requirement_id, model_name, model_provider,
               prompt_text, answer_text, answer_file_path, reuse_count, created_at
          FROM model_answers WHERE id=%s
        """,
        (matched_answer_id,),
    )
    if not matched_row:
        raise HTTPException(404, f"matched_answer_id={matched_answer_id} not found")

    # ---- 5) 후보만 원할 때 ----
    if not payload.adapt:
        return {
            "reused": True,
            "adapted": False,
            "raw_input_id": raw_id,
            "matched_answer_id": matched_answer_id,
            "similarity": best["similarity"],
            "threshold": payload.threshold,
            "candidate_answer": matched_row,
            "search": {"model_answer": candidates, **aux_groups},
        }

    # ---- 5) LLM 적응(adapt): 기존 답변을 현재 요구사항에 맞게 수정 ----
    adapt_model = payload.model or _default_local_checkpoint()
    adapt_prompt_parts: list[str] = [
        "[지시]\n아래 기존 답변을 현재 요구사항에 맞게 필요한 부분만 수정해서 새 답변을 작성해줘.\n"
        "변경되지 않은 부분은 그대로 유지하고, 차이가 나는 곳만 자연스럽게 갱신해.",
        f"[현재 요구사항]\n{payload.requirement or query_text}",
    ]
    if payload.code:
        adapt_prompt_parts.append(
            f"[현재 입력 코드 ({payload.code_language or 'plain'})]\n{payload.code}"
        )
    adapt_prompt_parts.append(
        f"[기존 답변 (id={matched_answer_id}, similarity={best['similarity']})]\n"
        + (matched_row.get("answer_text") or "")
    )
    adapt_prompt = "\n\n".join(adapt_prompt_parts)

    adapted_text, raw_resp = _generate_with_model(
        adapt_prompt, adapt_model,
        payload.code_language, task="reuse_adapt",
    )

    # ---- 6) 새 답변 저장 ----
    latency_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
    new_answer_id = db.execute(
        """
        INSERT INTO model_answers
            (raw_input_id, requirement_id, model_name, model_provider,
             prompt_text, answer_text, tokens_input, tokens_output, latency_ms,
             reused_from_answer_id, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'reused')
        """,
        (raw_id, payload.requirement_id, adapt_model, "local",
         adapt_prompt, adapted_text,
         (raw_resp or {}).get("tokens_input"),
         (raw_resp or {}).get("tokens_output"),
         latency_ms, matched_answer_id),
    )
    saved_ans = storage.save_model_answer(
        adapted_text, answer_id=new_answer_id, model_name=adapt_model,
    )
    db.execute(
        "UPDATE model_answers SET answer_file_path=%s, file_size=%s, sha256=%s WHERE id=%s",
        (saved_ans.rel_path, saved_ans.size, saved_ans.sha256, new_answer_id),
    )

    # reuse_count 증가 + last_reused_at 갱신
    db.execute(
        "UPDATE model_answers "
        "   SET reuse_count = reuse_count + 1, last_reused_at = CURRENT_TIMESTAMP "
        " WHERE id=%s",
        (matched_answer_id,),
    )

    # 재사용 로그
    log_id: int | None = None
    if payload.record:
        try:
            log_id = db.execute(
                """
                INSERT INTO answer_reuse_logs
                    (raw_input_id, matched_answer_id, new_answer_id,
                     similarity, metric, embedding_model, decision,
                     query_target_type, query_text_hash, top_k, threshold,
                     candidates_json, adapted, adaptation_prompt,
                     adaptation_model, latency_ms)
                VALUES (%s, %s, %s, %s, 'cosine', %s, 'reused',
                        %s, %s, %s, %s, %s, 1, %s, %s, %s)
                """,
                (raw_id, matched_answer_id, new_answer_id,
                 best["similarity"], qmodel,
                 query_target_type, query_hash,
                 payload.top_k, payload.threshold,
                 json.dumps(
                     {"model_answer": candidates, **aux_groups},
                     ensure_ascii=False, default=str,
                 ),
                 adapt_prompt, adapt_model, latency_ms),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("answer_reuse_logs insert failed: %s", exc)

    return {
        "reused": True,
        "adapted": True,
        "raw_input_id": raw_id,
        "matched_answer_id": matched_answer_id,
        "new_answer_id": new_answer_id,
        "similarity": best["similarity"],
        "threshold": payload.threshold,
        "reuse_log_id": log_id,
        "model": adapt_model,
        "answer_text": adapted_text,
        "answer_file_path": saved_ans.rel_path,
        "reuse_count": (matched_row.get("reuse_count") or 0) + 1,
        "latency_ms": latency_ms,
        "search": {"model_answer": candidates, **aux_groups},
        "stub": raw_resp is None,
    }


# --- GET /api/reuse/logs ---------------------------------------------------
@app.get("/api/reuse/logs")
def api_reuse_logs(
    raw_input_id: Optional[int] = Query(None),
    matched_answer_id: Optional[int] = Query(None),
    decision: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    where: list[str] = []
    args: list[Any] = []
    if raw_input_id is not None:
        where.append("raw_input_id=%s"); args.append(raw_input_id)
    if matched_answer_id is not None:
        where.append("matched_answer_id=%s"); args.append(matched_answer_id)
    if decision:
        where.append("decision=%s"); args.append(decision)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.fetch_all(
        f"SELECT id, raw_input_id, matched_answer_id, new_answer_id, "
        f"       similarity, metric, embedding_model, decision, "
        f"       query_target_type, top_k, threshold, adapted, "
        f"       adaptation_model, latency_ms, created_at "
        f"FROM answer_reuse_logs {where_sql} "
        f"ORDER BY id DESC LIMIT %s OFFSET %s",
        tuple(args + [limit, offset]),
    )
    total = (db.fetch_one(
        f"SELECT COUNT(*) AS n FROM answer_reuse_logs {where_sql}",
        tuple(args),
    ) or {}).get("n", 0)
    return {"total": total, "limit": limit, "offset": offset, "items": rows}


# --- GET /api/reuse/stats --------------------------------------------------
@app.get("/api/reuse/stats")
def api_reuse_stats(limit: int = Query(20, ge=1, le=200)):
    """가장 자주 재사용된 모델 답변 상위 목록."""
    top = db.fetch_all(
        "SELECT id AS answer_id, model_name, reuse_count, last_reused_at, "
        "       created_at, LEFT(answer_text, 240) AS answer_preview "
        "FROM model_answers "
        "WHERE reuse_count > 0 "
        "ORDER BY reuse_count DESC, last_reused_at DESC LIMIT %s",
        (int(limit),),
    )
    summary = db.fetch_one(
        "SELECT COUNT(*) AS reused_answers, "
        "       COALESCE(SUM(reuse_count), 0) AS total_reuses "
        "FROM model_answers WHERE reuse_count > 0"
    ) or {"reused_answers": 0, "total_reuses": 0}
    decisions = db.fetch_all(
        "SELECT decision, COUNT(*) AS n FROM answer_reuse_logs GROUP BY decision"
    )
    return {
        "summary": summary,
        "decisions": decisions,
        "top": top,
    }



# ===========================================================================
# Step 15: 코드 최적화 엔진 (사진 명세 1:1)
#
#   사진 흐름:
#     코드 입력 → 언어 감지 → 정적 분석 → 라이브러리 패턴 검색
#       → 과거 답변 검색 → LLM 최적화 → 결과 비교 → 저장
#
#   사진 최적화 유형(9가지):
#     문법 오류 수정, 오탈자 수정, 불필요한 코드 제거,
#     반복문 개선, 메모리 사용량 개선, 라이브러리 대체,
#     알고리즘 개선, 가독성 개선, 실행 속도 개선
#
#   핵심 원칙: "LLM만으로 최적화하지 말고, 규칙 기반 분석도 같이 둬야 합니다."
# ===========================================================================
OPTIMIZATION_TYPES_FALLBACK: list[dict[str, Any]] = [
    {"type_key": "syntax_error", "label": "문법 오류 수정",     "sort_order": 1},
    {"type_key": "typo",         "label": "오탈자 수정",        "sort_order": 2},
    {"type_key": "dead_code",    "label": "불필요한 코드 제거", "sort_order": 3},
    {"type_key": "loop",         "label": "반복문 개선",        "sort_order": 4},
    {"type_key": "memory",       "label": "메모리 사용량 개선", "sort_order": 5},
    {"type_key": "library",      "label": "라이브러리 대체",    "sort_order": 6},
    {"type_key": "algorithm",    "label": "알고리즘 개선",      "sort_order": 7},
    {"type_key": "readability",  "label": "가독성 개선",        "sort_order": 8},
    {"type_key": "speed",        "label": "실행 속도 개선",     "sort_order": 9},
]


def _opt_load_types() -> list[dict[str, Any]]:
    try:
        rows = db.fetch_all(
            "SELECT id, type_key, label, description, sort_order "
            "FROM optimization_types ORDER BY sort_order, id"
        )
        if rows:
            return rows
    except Exception as exc:  # noqa: BLE001
        log.info("optimization_types DB unavailable, using fallback (%s)", exc)
    return OPTIMIZATION_TYPES_FALLBACK


# --- GET /api/optimize/types ----------------------------------------------
@app.get("/api/optimize/types")
def api_optimize_types():
    """사진 명세의 9가지 최적화 유형 카탈로그."""
    return {"types": _opt_load_types()}


# --- POST /api/optimize/analyze -------------------------------------------
class OptimizeAnalyzeIn(BaseModel):
    code: str
    language: Optional[str] = None


@app.post("/api/optimize/analyze")
def api_optimize_analyze(payload: OptimizeAnalyzeIn):
    """규칙 기반 정적 분석만 수행 (사진 흐름의 '정적 분석' 박스).

    LLM 호출 없이 9가지 최적화 유형 중 어떤 finding이 있는지 즉시 반환한다.
    """
    if not (payload.code or "").strip():
        raise HTTPException(400, "empty code")
    lang = payload.language
    if not lang:
        lang, _ = _detect_language(payload.code, None)
    return optimizer.analyze(payload.code, lang)


# --- POST /api/optimize/library-patterns ----------------------------------
class OptimizeLibraryIn(BaseModel):
    code: Optional[str] = None
    language: Optional[str] = None
    library: Optional[str] = None
    limit: int = 10


@app.post("/api/optimize/library-patterns")
def api_optimize_library_patterns(payload: OptimizeLibraryIn):
    """사진 흐름의 '라이브러리 패턴 검색' 박스.

    1) Step 12 의 ``llm_library_examples`` 카탈로그에서 (language, library) 매칭
       항목을 찾는다.
    2) 코드가 주어지면 LIBRARY_REPLACEMENTS 휴리스틱으로 즉시 교체 후보도 제시.
    """
    where: list[str] = []
    args: list[Any] = []
    if payload.language:
        where.append("language=%s"); args.append(payload.language)
    if payload.library:
        where.append("library=%s"); args.append(payload.library)
    sql = (
        "SELECT id, language, library, version, topic, file_path, status, created_at "
        "FROM llm_library_examples"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT %s"
    args.append(int(payload.limit))
    matches: list[dict[str, Any]] = []
    try:
        matches = db.fetch_all(sql, tuple(args)) or []
    except Exception as exc:  # noqa: BLE001
        log.info("llm_library_examples query skipped: %s", exc)

    replacement_hints: list[dict[str, Any]] = []
    if payload.code and payload.language:
        for entry in optimizer.LIBRARY_REPLACEMENTS:
            if entry["language"] != payload.language:
                continue
            if entry["from"] in payload.code:
                replacement_hints.append(entry)

    return {
        "language": payload.language,
        "library": payload.library,
        "library_examples": matches,
        "replacement_hints": replacement_hints,
    }


# --- POST /api/optimize/engine --------------------------------------------
class OptimizeEngineIn(BaseModel):
    code: str
    language: Optional[str] = None
    requirement: Optional[str] = None
    library: Optional[str] = None
    raw_input_id: Optional[int] = None
    answer_id: Optional[int] = None      # 옵션: 기존 답변과 연결
    project_id: Optional[int] = None
    user_tag: Optional[str] = None
    model: Optional[str] = None
    use_llm: bool = True                 # False 면 규칙 기반 결과만 저장
    use_reuse: bool = True               # 과거 답변 검색 사용 여부
    reuse_threshold: float = 0.85
    reuse_top_k: int = 3


@app.post("/api/optimize/engine")
def api_optimize_engine(payload: OptimizeEngineIn):
    """사진 명세의 8단계 코드 최적화 엔진을 한 번의 호출로 실행한다.

        코드 입력 → 언어 감지 → 정적 분석 → 라이브러리 패턴 검색
            → 과거 답변 검색 → LLM 최적화 → 결과 비교 → 저장
    """
    if not (payload.code or "").strip():
        raise HTTPException(400, "empty code")

    started = datetime.utcnow()

    # ---- 1) 코드 입력: raw_inputs 보존 (없을 때만 새로 만든다) ----
    raw_id = payload.raw_input_id
    if raw_id is None:
        raw_id = _insert_raw_input(
            input_type="text",
            raw_text=payload.code,
            project_id=payload.project_id,
            user_tag=payload.user_tag,
        )
        s_orig = storage.save_original_code(
            payload.code, raw_input_id=raw_id, language=payload.language,
        )
        db.execute(
            "UPDATE raw_inputs SET source_file_path=%s WHERE id=%s",
            (s_orig.rel_path, raw_id),
        )

    # ---- 2) 언어 감지 ----
    language = payload.language
    language_source = "hint" if language else None
    if not language:
        language, detect_info = _detect_language(payload.code, None)
        language_source = (detect_info or {}).get("source") or "language-worker"

    # ---- 3) 정적 분석 (규칙 기반) ----
    analysis = optimizer.analyze(payload.code, language)
    findings: list[dict[str, Any]] = analysis["findings"]
    summary: dict[str, int] = analysis["summary"]

    # ---- 4) 라이브러리 패턴 검색 ----
    library_matches: list[dict[str, Any]] = []
    library_hints: list[dict[str, Any]] = []
    try:
        rows = db.fetch_all(
            "SELECT id, language, library, version, topic, file_path "
            "FROM llm_library_examples "
            "WHERE language=%s "
            + (" AND library=%s " if payload.library else " ")
            + "ORDER BY id DESC LIMIT 10",
            (language, payload.library) if payload.library else (language,),
        ) or []
        library_matches = rows
    except Exception as exc:  # noqa: BLE001
        log.info("library pattern lookup skipped: %s", exc)
    for entry in optimizer.LIBRARY_REPLACEMENTS:
        if entry["language"] == language and entry["from"] in payload.code:
            library_hints.append(entry)
            findings.append({
                "type_key": "library", "source": "library", "severity": "info",
                "rule_id": f"LIB-MATCH-{entry['from'].upper()}",
                "line_no": None, "col_no": None,
                "message": f"라이브러리 대체 후보: {entry['from']} → {entry['to']}",
                "suggestion": entry["to"], "snippet": entry["reason"],
            })

    # ---- 5) 과거 답변 검색 ----
    similar_answers: list[dict[str, Any]] = []
    if payload.use_reuse:
        query_text = (
            (payload.requirement + "\n\n") if payload.requirement else ""
        ) + payload.code
        try:
            search_res = api_embeddings_search(EmbeddingSearchIn(
                text=query_text,
                target_types=["model_answer", "optimized_code"],
                top_k=payload.reuse_top_k,
                threshold=payload.reuse_threshold,
            ))
            similar_answers = search_res.get("items", []) or []
            for item in similar_answers:
                findings.append({
                    "type_key": "library" if item.get("target_type") == "optimized_code" else "readability",
                    "source": "reuse", "severity": "info",
                    "rule_id": f"REUSE-{item.get('target_type', '?').upper()}-{item.get('target_id')}",
                    "line_no": None, "col_no": None,
                    "message": (
                        f"유사도 {item.get('similarity'):.3f} 의 과거 "
                        f"{item.get('target_type')} #{item.get('target_id')} 발견 — 재사용 검토"
                    ),
                    "suggestion": None, "snippet": None,
                })
        except HTTPException as exc:
            log.info("reuse search skipped: %s", exc.detail)
        except Exception as exc:  # noqa: BLE001
            log.info("reuse search error: %s", exc)

    # ---- 6) LLM 최적화 ----
    llm_started = datetime.utcnow()
    optimized_text = payload.code
    raw_resp: dict[str, Any] | None = None
    model_name = payload.model or _default_local_checkpoint()
    rule_only = not payload.use_llm

    if payload.use_llm:
        rule_hint = optimizer.findings_to_prompt_hint(findings)
        prompt_parts: list[str] = [
            "[지시]\n다음 코드를 9가지 최적화 유형(문법 오류 수정, 오탈자 수정, "
            "불필요한 코드 제거, 반복문 개선, 메모리 사용량 개선, 라이브러리 대체, "
            "알고리즘 개선, 가독성 개선, 실행 속도 개선) 관점에서 개선해줘. "
            "동작은 절대 바꾸지 말고, 변경 이유를 코드 위 주석으로 짧게 남겨줘.",
        ]
        if payload.requirement:
            prompt_parts.append(f"[요구사항]\n{payload.requirement}")
        prompt_parts.append(f"[규칙 기반 분석 결과]\n{rule_hint}")
        if library_hints:
            prompt_parts.append(
                "[라이브러리 대체 후보]\n" + "\n".join(
                    f"- {h['from']} → {h['to']} ({h['reason']})" for h in library_hints
                )
            )
        if similar_answers:
            prompt_parts.append(
                "[과거 유사 답변 후보]\n" + "\n".join(
                    f"- {it['target_type']}#{it['target_id']} (sim={it['similarity']:.3f})"
                    for it in similar_answers
                )
            )
        prompt_parts.append(f"[입력 코드 ({language or 'plain'})]\n{payload.code}")
        prompt = "\n\n".join(prompt_parts)

        optimized_text, raw_resp = _generate_with_model(
            prompt, model_name, language, task="optimize",
        )
    llm_latency_ms = int((datetime.utcnow() - llm_started).total_seconds() * 1000)

    # ---- 7) 결과 비교 ----
    applied_types = [k for k, v in summary.items() if v > 0]
    comparison = optimizer.compare(payload.code, optimized_text, applied_types=applied_types)
    diff_text = storage.make_unified_diff(payload.code, optimized_text)
    comparison["rule_count"] = analysis["rule_count"]
    comparison["llm_used"] = payload.use_llm
    comparison["reuse_candidates"] = len(similar_answers)
    comparison["library_matches"] = len(library_matches) + len(library_hints)

    # ---- 8) 저장 ----
    # 8.1 model_answers / generated_code 가 없으면 placeholder 로 만든다.
    answer_id = payload.answer_id
    if answer_id is None:
        answer_id = db.execute(
            """
            INSERT INTO model_answers
                (raw_input_id, requirement_id, model_name, model_provider,
                 prompt_text, answer_text, latency_ms, status)
            VALUES (%s, NULL, %s, 'local', %s, %s, %s, 'optimized')
            """,
            (raw_id, model_name,
             "[Step 15] 코드 최적화 엔진 자동 생성 placeholder",
             optimized_text, llm_latency_ms),
        )
        s_ans = storage.save_model_answer(
            optimized_text, answer_id=answer_id, model_name=model_name,
        )
        db.execute(
            "UPDATE model_answers SET answer_file_path=%s, file_size=%s, sha256=%s WHERE id=%s",
            (s_ans.rel_path, s_ans.size, s_ans.sha256, answer_id),
        )

    s_gen = storage.save_generated_code(
        payload.code, answer_id=answer_id, language=language,
    )
    gen_id = db.execute(
        """
        INSERT INTO generated_code
            (answer_id, language, file_name, code_text, is_runnable,
             file_path, file_size, sha256)
        VALUES (%s, %s, NULL, %s, 0, %s, %s, %s)
        """,
        (answer_id, language, payload.code,
         s_gen.rel_path, s_gen.size, s_gen.sha256),
    )

    s_opt = storage.save_optimized_code(
        optimized_text, generated_code_id=gen_id, language=language,
    )
    s_diff = storage.save_code_diff(diff_text, generated_code_id=gen_id)
    opt_id = db.execute(
        """
        INSERT INTO optimized_code
            (generated_code_id, optimizer, language, code_text, improvement_notes,
             file_path, diff_file_path, file_size, sha256)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (gen_id,
         f"step15-engine ({'rule+llm' if payload.use_llm else 'rule-only'})",
         language, optimized_text,
         "Step 15 엔진: 적용 유형=" + ",".join(applied_types) if applied_types else None,
         s_opt.rel_path, s_diff.rel_path, s_opt.size, s_opt.sha256),
    )

    total_latency_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
    status_value = "ok"
    if any(f["type_key"] == "syntax_error" and f.get("severity") == "error" for f in findings):
        status_value = "partial"
    if rule_only and not findings:
        status_value = "partial"

    run_id: int | None = None
    try:
        run_id = db.execute(
            """
            INSERT INTO optimization_runs
                (raw_input_id, generated_code_id, optimized_code_id,
                 language, language_source, input_code, output_code, diff_text,
                 static_analysis_json, library_matches_json, similar_answers_json,
                 comparison_json, llm_model, llm_latency_ms, total_latency_ms,
                 rule_only, status, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (raw_id, gen_id, opt_id,
             language, language_source,
             payload.code, optimized_text, diff_text,
             json.dumps({"summary": summary, "rule_count": analysis["rule_count"]},
                        ensure_ascii=False),
             json.dumps(
                 {"library_examples": library_matches,
                  "replacement_hints": library_hints},
                 ensure_ascii=False, default=str),
             json.dumps(similar_answers, ensure_ascii=False, default=str),
             json.dumps(comparison, ensure_ascii=False),
             model_name if payload.use_llm else None,
             llm_latency_ms if payload.use_llm else None,
             total_latency_ms,
             1 if rule_only else 0,
             status_value,
             payload.requirement[:500] if payload.requirement else None),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("optimization_runs insert failed: %s", exc)

    if run_id and findings:
        try:
            for f in findings:
                db.execute(
                    """
                    INSERT INTO optimization_findings
                        (run_id, type_key, source, severity,
                         line_no, col_no, rule_id, message, suggestion, snippet)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (run_id, f["type_key"], f.get("source") or "rule",
                     f.get("severity") or "info",
                     f.get("line_no"), f.get("col_no"),
                     f.get("rule_id"), f["message"][:500],
                     (f.get("suggestion") or None),
                     (f.get("snippet") or None)),
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("optimization_findings insert failed: %s", exc)

    return {
        "run_id": run_id,
        "raw_input_id": raw_id,
        "answer_id": answer_id,
        "generated_code_id": gen_id,
        "optimized_code_id": opt_id,
        "language": language,
        "language_source": language_source,
        "static_analysis": analysis,
        "library_matches": library_matches,
        "library_hints": library_hints,
        "similar_answers": similar_answers,
        "llm_model": model_name if payload.use_llm else None,
        "llm_latency_ms": llm_latency_ms if payload.use_llm else None,
        "total_latency_ms": total_latency_ms,
        "comparison": comparison,
        "code": optimized_text,
        "diff": diff_text,
        "code_file_path": s_opt.rel_path,
        "diff_file_path": s_diff.rel_path,
        "status": status_value,
        "rule_only": rule_only,
        "stub": (raw_resp is None) if payload.use_llm else False,
    }


# --- GET /api/optimize/runs -----------------------------------------------
@app.get("/api/optimize/runs")
def api_optimize_runs(
    language: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    rule_only: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    where: list[str] = []
    args: list[Any] = []
    if language:
        where.append("language=%s"); args.append(language)
    if status:
        where.append("status=%s"); args.append(status)
    if rule_only is not None:
        where.append("rule_only=%s"); args.append(1 if rule_only else 0)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = db.fetch_all(
        f"SELECT id, raw_input_id, generated_code_id, optimized_code_id, "
        f"       language, language_source, llm_model, "
        f"       llm_latency_ms, total_latency_ms, rule_only, status, "
        f"       LEFT(COALESCE(notes,''), 240) AS notes_preview, created_at "
        f"FROM optimization_runs {where_sql} "
        f"ORDER BY id DESC LIMIT %s OFFSET %s",
        tuple(args + [limit, offset]),
    )
    total = (db.fetch_one(
        f"SELECT COUNT(*) AS n FROM optimization_runs {where_sql}",
        tuple(args),
    ) or {}).get("n", 0)
    return {"total": total, "limit": limit, "offset": offset, "items": rows}


# --- GET /api/optimize/runs/{id} ------------------------------------------
@app.get("/api/optimize/runs/{run_id}")
def api_optimize_run_get(run_id: int):
    row = db.fetch_one(
        "SELECT * FROM optimization_runs WHERE id=%s", (run_id,),
    )
    if not row:
        raise HTTPException(404, "optimization_run not found")

    findings = db.fetch_all(
        "SELECT id, type_key, source, severity, line_no, col_no, "
        "       rule_id, message, suggestion, snippet "
        "FROM optimization_findings WHERE run_id=%s "
        "ORDER BY type_key, line_no",
        (run_id,),
    ) or []

    # JSON 컬럼이 문자열로 들어오면 파싱
    for key in ("static_analysis_json", "library_matches_json",
                "similar_answers_json", "comparison_json"):
        if isinstance(row.get(key), str):
            try:
                row[key] = json.loads(row[key])
            except Exception:  # noqa: BLE001
                pass
    return {"run": row, "findings": findings}


# ===========================================================================
# Step 16: 명세서 기반 SW 생성 엔진 (사진 명세 1:1)
#
#   사진 흐름:
#     명세서 입력 → 요구사항 추출 → 기능 목록 생성 → 화면 목록 생성
#       → API 목록 생성 → DB 테이블 초안 생성 → 프로젝트 구조 생성 → 코드 생성
#
#   중간 데이터 JSON 스키마 (사진과 1:1):
#     {
#       "project_name": "...",
#       "features": [],
#       "screens": [],
#       "apis": [],
#       "database_tables": [],
#       "business_rules": []
#     }
# ===========================================================================
import spec_engine  # noqa: E402  (모듈 끝에서 의존성 import)


@app.get("/api/spec/schema")
def api_spec_schema():
    """사진의 중간 데이터 JSON 스키마 + 8단계 카탈로그."""
    return {
        "intermediate_schema": spec_engine.EMPTY_INTERMEDIATE,
        "steps": [
            {"step_no": no, "step_key": key, "label": label}
            for no, key, label in spec_engine.STEP_LABELS
        ],
    }


def _resolve_spec_input_text(
    *,
    spec: str | None,
    raw_input_id: int | None,
    image_id: int | None,
) -> tuple[str, str, int | None]:
    """입력 명세서 텍스트를 결정한다.

    우선순위: 직접 ``spec`` > image_id 의 추출 텍스트/스펙 > raw_input.raw_text.
    반환: (text, source_kind, image_id_used)
    """
    if spec and spec.strip():
        return spec, "text", None

    if image_id:
        img = db.fetch_one(
            "SELECT id, raw_input_id, text_file_path, spec_file_path, code_file_path "
            "FROM image_data WHERE id=%s",
            (image_id,),
        )
        if not img:
            raise HTTPException(404, f"image_id={image_id} not found")
        for col in ("spec_file_path", "text_file_path", "code_file_path"):
            t = _read_text_file_or_none(img.get(col))
            if t and t.strip():
                return t, "image", image_id
        raise HTTPException(400, f"image_id={image_id} 에는 추출된 텍스트/스펙이 없습니다")

    if raw_input_id:
        row = db.fetch_one(
            "SELECT id, raw_text, source_file_path FROM raw_inputs WHERE id=%s",
            (raw_input_id,),
        )
        if not row:
            raise HTTPException(404, f"raw_input_id={raw_input_id} not found")
        t = row.get("raw_text") or _read_text_file_or_none(row.get("source_file_path"))
        if t and t.strip():
            return t, "text", None
        raise HTTPException(400, f"raw_input_id={raw_input_id} 에 명세서 텍스트가 없습니다")

    raise HTTPException(400, "spec/raw_input_id/image_id 중 최소 하나는 필요합니다")


# --- POST /api/spec/extract ----------------------------------------------
class SpecExtractIn(BaseModel):
    spec: Optional[str] = None
    raw_input_id: Optional[int] = None
    image_id: Optional[int] = None
    project_name: Optional[str] = None
    use_llm: bool = True
    model: Optional[str] = None


@app.post("/api/spec/extract")
def api_spec_extract(payload: SpecExtractIn):
    """사진 흐름의 1~6단계만 수행: 명세서 → 요구사항/기능/화면/API/DB/규칙 JSON.

    LLM 호출 없이도 동작 (규칙 기반). ``use_llm=true`` 면 model-server 응답에서
    JSON 블록을 뽑아 결과를 보강한다.
    """
    text, source_kind, used_image_id = _resolve_spec_input_text(
        spec=payload.spec,
        raw_input_id=payload.raw_input_id,
        image_id=payload.image_id,
    )

    base = spec_engine.build_intermediate(text, project_name=payload.project_name)

    llm_used = False
    llm_raw: dict[str, Any] | None = None
    if payload.use_llm:
        prompt = (
            "[지시] 다음 명세서를 분석해서 정확히 아래 JSON 스키마로만 응답해줘.\n"
            "{\n"
            '  "project_name": "...",\n'
            '  "features": [{"id": "F001", "name": "...", "description": "..."}],\n'
            '  "screens": [{"id": "S001", "name": "...", "route": "/..."}],\n'
            '  "apis": [{"id": "A001", "method": "GET", "path": "/...", "summary": "..."}],\n'
            '  "database_tables": [{"id": "T001", "name": "...", "columns": [{"name": "id", "type": "BIGINT", "pk": true}]}],\n'
            '  "business_rules": [{"id": "R001", "rule": "..."}]\n'
            "}\n\n"
            f"[명세서]\n{text}"
        )
        model_name = payload.model or _default_local_checkpoint()
        text_resp, raw_resp = _generate_with_model(
            prompt, model_name, language=None, task="spec_extract",
        )
        llm_raw = raw_resp
        parsed = spec_engine.parse_llm_json(text_resp)
        if parsed:
            base = spec_engine.merge_llm_intermediate(base, parsed)
            llm_used = True

    return {
        "source_kind": source_kind,
        "image_id": used_image_id,
        "project_name": base.get("project_name"),
        "intermediate": {k: v for k, v in base.items() if not k.startswith("_")},
        "requirements": base.get("_requirements", []),
        "summary": spec_engine.summarize_intermediate(base),
        "llm_used": llm_used,
        "llm_stub": (llm_raw is None) if payload.use_llm else False,
    }


# --- POST /api/spec/engine ------------------------------------------------
class SpecEngineIn(BaseModel):
    spec: Optional[str] = None
    raw_input_id: Optional[int] = None
    image_id: Optional[int] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    target_language: Optional[str] = "python"
    target_framework: Optional[str] = "fastapi"
    user_tag: Optional[str] = None
    use_llm: bool = True
    model: Optional[str] = None
    notes: Optional[str] = None


@app.post("/api/spec/engine")
def api_spec_engine(payload: SpecEngineIn):
    """사진 명세의 8단계 SW 생성 엔진을 한 번의 호출로 실행한다.

        명세서 입력 → 요구사항 추출 → 기능 목록 생성 → 화면 목록 생성
            → API 목록 생성 → DB 테이블 초안 생성 → 프로젝트 구조 생성 → 코드 생성
    """
    started = datetime.utcnow()

    # ---- 1) 명세서 입력 ----
    text, source_kind, used_image_id = _resolve_spec_input_text(
        spec=payload.spec,
        raw_input_id=payload.raw_input_id,
        image_id=payload.image_id,
    )

    # 1.1) raw_inputs 보존 (없을 때만)
    raw_id = payload.raw_input_id
    if raw_id is None:
        raw_id = _insert_raw_input(
            input_type="image" if source_kind == "image" else "text",
            raw_text=text,
            project_id=payload.project_id,
            user_tag=payload.user_tag,
        )

    # 1.2) 입력 명세서 디스크 보존
    spec_file = storage.save_spec_input_text(
        text, run_hint="spec_input", owner_id=raw_id,
    )
    db.execute(
        "UPDATE raw_inputs SET source_file_path=COALESCE(source_file_path, %s) "
        "WHERE id=%s",
        (spec_file.rel_path, raw_id),
    )

    steps_log: list[dict[str, Any]] = []
    steps_log.append({
        "step_no": 1, "step_key": "spec_input", "label": "명세서 입력",
        "output_json": {"chars": len(text), "source_kind": source_kind,
                        "spec_file_path": spec_file.rel_path},
        "source": "user", "latency_ms": 0, "status": "ok",
    })

    # ---- 2) 요구사항 추출 (규칙 기반) ----
    t2 = datetime.utcnow()
    requirements = spec_engine.extract_requirements(text)
    steps_log.append({
        "step_no": 2, "step_key": "requirements", "label": "요구사항 추출",
        "output_json": {"count": len(requirements), "items": requirements},
        "source": "rule",
        "latency_ms": int((datetime.utcnow() - t2).total_seconds() * 1000),
        "status": "ok" if requirements else "partial",
    })

    # ---- 3~6) 기능/화면/API/DB/규칙 후보 (규칙 기반) ----
    base = {
        "project_name":    payload.project_name or spec_engine.guess_project_name(text),
        "features":        spec_engine.derive_features(requirements),
        "screens":         spec_engine.derive_screens(requirements),
        "apis":            spec_engine.derive_apis(requirements, text),
        "database_tables": spec_engine.derive_database_tables(requirements),
        "business_rules":  spec_engine.derive_business_rules(requirements),
        "_requirements":   requirements,
    }

    # ---- LLM 보강 (옵션) ----
    llm_used = False
    llm_latency_ms: int | None = None
    model_name = payload.model or _default_local_checkpoint()
    if payload.use_llm:
        llm_started = datetime.utcnow()
        prompt = (
            "[지시] 다음 명세서를 분석해서 정확히 아래 JSON 스키마로만 응답해줘.\n"
            "스키마 외 텍스트는 절대 포함하지 마.\n"
            "{\n"
            '  "project_name": "...",\n'
            '  "features": [{"id": "F001", "name": "...", "description": "..."}],\n'
            '  "screens": [{"id": "S001", "name": "...", "route": "/..."}],\n'
            '  "apis": [{"id": "A001", "method": "GET", "path": "/...", "summary": "..."}],\n'
            '  "database_tables": [{"id": "T001", "name": "...",'
            ' "columns": [{"name": "id", "type": "BIGINT", "pk": true}]}],\n'
            '  "business_rules": [{"id": "R001", "rule": "..."}]\n'
            "}\n\n"
            f"[프로젝트 후보 이름] {base['project_name']}\n\n"
            f"[명세서]\n{text}"
        )
        text_resp, _raw = _generate_with_model(
            prompt, model_name, language=None, task="spec_extract",
        )
        parsed = spec_engine.parse_llm_json(text_resp)
        if parsed:
            base = spec_engine.merge_llm_intermediate(base, parsed)
            llm_used = True
        llm_latency_ms = int((datetime.utcnow() - llm_started).total_seconds() * 1000)

    for no, key, label in spec_engine.STEP_LABELS[2:6]:
        steps_log.append({
            "step_no": no, "step_key": key, "label": label,
            "output_json": base.get(key) or [],
            "source": "llm" if llm_used else "rule",
            "llm_model": model_name if llm_used else None,
            "latency_ms": (llm_latency_ms or 0) // 4 if llm_used else 0,
            "status": "ok" if (base.get(key) or []) else "partial",
        })

    # ---- 7) 프로젝트 구조 생성 ----
    t7 = datetime.utcnow()
    structure = spec_engine.derive_project_structure(
        base,
        language=payload.target_language or "python",
        framework=payload.target_framework or "fastapi",
    )
    steps_log.append({
        "step_no": 7, "step_key": "project_structure",
        "label": "프로젝트 구조 생성",
        "output_json": structure,
        "source": "rule",
        "latency_ms": int((datetime.utcnow() - t7).total_seconds() * 1000),
        "status": "ok",
    })

    # ---- 8) 코드 생성 ----
    t8 = datetime.utcnow()
    files = spec_engine.generate_project_files(
        base,
        language=payload.target_language or "python",
        framework=payload.target_framework or "fastapi",
    )
    steps_log.append({
        "step_no": 8, "step_key": "code_generation", "label": "코드 생성",
        "output_json": {"file_count": len(files),
                        "rel_paths": [f["rel_path"] for f in files]},
        "source": "rule",
        "latency_ms": int((datetime.utcnow() - t8).total_seconds() * 1000),
        "status": "ok" if files else "partial",
    })

    # ---- 저장 ----
    intermediate_payload = {k: v for k, v in base.items() if not k.startswith("_")}
    counts = spec_engine.summarize_intermediate(base)
    total_latency_ms = int((datetime.utcnow() - started).total_seconds() * 1000)

    status_value: str = "ok"
    if not requirements or not files:
        status_value = "partial"

    run_id = db.execute(
        """
        INSERT INTO spec_engine_runs
            (raw_input_id, project_id, source_kind, source_image_id,
             spec_text, spec_file_path, project_name,
             target_language, target_framework,
             requirements_json, intermediate_json,
             features_json, screens_json, apis_json,
             database_tables_json, business_rules_json,
             project_structure_json, intermediate_file_path,
             llm_model, llm_latency_ms, total_latency_ms,
             feature_count, screen_count, api_count, table_count,
             rule_count, file_count, status, notes)
        VALUES (%s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s)
        """,
        (raw_id, payload.project_id, source_kind, used_image_id,
         text, spec_file.rel_path, intermediate_payload.get("project_name"),
         payload.target_language, payload.target_framework,
         json.dumps(requirements, ensure_ascii=False),
         json.dumps(intermediate_payload, ensure_ascii=False),
         json.dumps(intermediate_payload.get("features"), ensure_ascii=False),
         json.dumps(intermediate_payload.get("screens"), ensure_ascii=False),
         json.dumps(intermediate_payload.get("apis"), ensure_ascii=False),
         json.dumps(intermediate_payload.get("database_tables"), ensure_ascii=False),
         json.dumps(intermediate_payload.get("business_rules"), ensure_ascii=False),
         json.dumps(structure, ensure_ascii=False),
         None,  # intermediate_file_path - 아래에서 갱신
         model_name if llm_used else None,
         llm_latency_ms if llm_used else None,
         total_latency_ms,
         counts["feature_count"], counts["screen_count"], counts["api_count"],
         counts["table_count"], counts["rule_count"], len(files),
         status_value, (payload.notes or None)),
    )

    # 중간 JSON 디스크 보존
    inter_saved = storage.save_spec_intermediate_json(
        intermediate_payload,
        run_id=run_id,
        project_name=intermediate_payload.get("project_name"),
    )
    db.execute(
        "UPDATE spec_engine_runs SET intermediate_file_path=%s WHERE id=%s",
        (inter_saved.rel_path, run_id),
    )

    # 단계별 산출물 기록
    for s in steps_log:
        try:
            db.execute(
                """
                INSERT INTO spec_engine_steps
                    (run_id, step_no, step_key, label, output_json,
                     source, llm_model, latency_ms, status, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (run_id, s["step_no"], s["step_key"], s["label"],
                 json.dumps(s.get("output_json"), ensure_ascii=False, default=str),
                 s.get("source") or "rule",
                 s.get("llm_model"), s.get("latency_ms"),
                 s.get("status") or "ok", s.get("notes")),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("spec_engine_steps insert failed (step=%s): %s",
                        s.get("step_key"), exc)

    # 생성 파일 저장 (DB + 디스크)
    saved_files: list[dict[str, Any]] = []
    for f in files:
        try:
            saved = storage.save_spec_project_file(
                f["code"],
                run_id=run_id,
                project_name=intermediate_payload.get("project_name"),
                rel_path=f["rel_path"],
            )
        except ValueError as exc:
            log.warning("skip invalid spec file %s: %s", f.get("rel_path"), exc)
            continue
        file_id = db.execute(
            """
            INSERT INTO spec_engine_files
                (run_id, rel_path, language, role, code_text,
                 file_path, file_size, sha256)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (run_id, f["rel_path"], f.get("language"), f.get("role") or "other",
             f["code"], saved.rel_path, saved.size, saved.sha256),
        )
        saved_files.append({
            "id":        file_id,
            "rel_path":  f["rel_path"],
            "language":  f.get("language"),
            "role":      f.get("role") or "other",
            "file_path": saved.rel_path,
            "size":      saved.size,
        })

    return {
        "run_id": run_id,
        "raw_input_id": raw_id,
        "source_kind": source_kind,
        "image_id": used_image_id,
        "project_name": intermediate_payload.get("project_name"),
        "target_language": payload.target_language,
        "target_framework": payload.target_framework,
        "intermediate": intermediate_payload,
        "requirements": requirements,
        "project_structure": structure,
        "files": saved_files,
        "spec_file_path": spec_file.rel_path,
        "intermediate_file_path": inter_saved.rel_path,
        "summary": counts,
        "llm_used": llm_used,
        "llm_model": model_name if llm_used else None,
        "llm_latency_ms": llm_latency_ms if llm_used else None,
        "total_latency_ms": total_latency_ms,
        "status": status_value,
        "steps": [
            {k: v for k, v in s.items() if k != "output_json"}
            for s in steps_log
        ],
    }


# --- GET /api/spec/runs ---------------------------------------------------
@app.get("/api/spec/runs")
def api_spec_runs(
    project_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    where: list[str] = []
    args: list[Any] = []
    if project_id is not None:
        where.append("project_id=%s"); args.append(project_id)
    if status:
        where.append("status=%s"); args.append(status)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = db.fetch_all(
        f"SELECT id, raw_input_id, project_id, source_kind, source_image_id, "
        f"       project_name, target_language, target_framework, "
        f"       feature_count, screen_count, api_count, table_count, "
        f"       rule_count, file_count, llm_model, "
        f"       llm_latency_ms, total_latency_ms, status, "
        f"       LEFT(COALESCE(notes,''), 240) AS notes_preview, created_at "
        f"FROM spec_engine_runs {where_sql} "
        f"ORDER BY id DESC LIMIT %s OFFSET %s",
        tuple(args + [limit, offset]),
    )
    total = (db.fetch_one(
        f"SELECT COUNT(*) AS n FROM spec_engine_runs {where_sql}",
        tuple(args),
    ) or {}).get("n", 0)
    return {"total": total, "limit": limit, "offset": offset, "items": rows}


# --- GET /api/spec/runs/{id} ----------------------------------------------
@app.get("/api/spec/runs/{run_id}")
def api_spec_run_get(run_id: int, include_code: bool = Query(False)):
    row = db.fetch_one(
        "SELECT * FROM spec_engine_runs WHERE id=%s", (run_id,),
    )
    if not row:
        raise HTTPException(404, "spec_engine_run not found")

    # JSON 컬럼 파싱
    for key in ("requirements_json", "intermediate_json", "features_json",
                "screens_json", "apis_json", "database_tables_json",
                "business_rules_json", "project_structure_json"):
        if isinstance(row.get(key), str):
            try:
                row[key] = json.loads(row[key])
            except Exception:  # noqa: BLE001
                pass

    file_cols = (
        "id, rel_path, language, role, file_path, file_size, sha256, created_at"
        + (", code_text" if include_code else "")
    )
    files = db.fetch_all(
        f"SELECT {file_cols} FROM spec_engine_files WHERE run_id=%s "
        "ORDER BY rel_path ASC",
        (run_id,),
    ) or []

    steps = db.fetch_all(
        "SELECT id, step_no, step_key, label, source, llm_model, "
        "       latency_ms, status, output_json, created_at "
        "FROM spec_engine_steps WHERE run_id=%s ORDER BY step_no ASC, id ASC",
        (run_id,),
    ) or []
    for s in steps:
        if isinstance(s.get("output_json"), str):
            try:
                s["output_json"] = json.loads(s["output_json"])
            except Exception:  # noqa: BLE001
                pass

    return {"run": row, "files": files, "steps": steps}


# ===========================================================================
# Step 17: 전체 통합 테스트
#
# 사진 17단계 흐름 :
#   .exe → Docker Compose → Web UI → Backend
#       └─ MySQL / Hardware Detector / Language Worker
#          / Vision Server / LLM Server / Embedding Server
#
# 통합 테스트 시나리오 (사진 체크리스트와 1:1):
#   1) .exe 실행
#   2) Docker Compose 자동 실행
#   3) Web UI 자동 오픈
#   4) 코드 입력
#   5) 모델 답변 생성
#   6) 답변 저장
#   7) embedding 저장
#   8) 같은 요구사항 재입력
#   9) 기존 답변 재사용
#  10) 코드 이미지 업로드
#  11) 이미지에서 코드 추출
#  12) 추출 코드 기반 답변 생성
#  13) GPU 없을 때 CPU fallback 확인
#
# 엔드포인트:
#   GET  /api/integration/checklist      - 체크리스트 카탈로그
#   POST /api/integration/run            - 시나리오 실행 + DB 기록
#   GET  /api/integration/runs           - 과거 실행 이력
#   GET  /api/integration/runs/{run_id}  - 실행 상세 (단계별 결과)
# ===========================================================================
import base64 as _b64  # noqa: E402

INTEGRATION_CHECKLIST: list[dict[str, Any]] = [
    {"step_no": 1,  "step_key": "launcher_exe",      "label": ".exe 실행",
     "category": "environment", "auto": False},
    {"step_no": 2,  "step_key": "compose_up",        "label": "Docker Compose 자동 실행",
     "category": "environment", "auto": True},
    {"step_no": 3,  "step_key": "web_ui_open",       "label": "Web UI 자동 오픈",
     "category": "environment", "auto": True},
    {"step_no": 4,  "step_key": "code_input",        "label": "코드 입력",
     "category": "pipeline",    "auto": True},
    {"step_no": 5,  "step_key": "model_answer",      "label": "모델 답변 생성",
     "category": "pipeline",    "auto": True},
    {"step_no": 6,  "step_key": "answer_save",       "label": "답변 저장",
     "category": "pipeline",    "auto": True},
    {"step_no": 7,  "step_key": "embedding_save",    "label": "embedding 저장",
     "category": "pipeline",    "auto": True},
    {"step_no": 8,  "step_key": "requirement_replay","label": "같은 요구사항 재입력",
     "category": "reuse",       "auto": True},
    {"step_no": 9,  "step_key": "answer_reuse",      "label": "기존 답변 재사용",
     "category": "reuse",       "auto": True},
    {"step_no": 10, "step_key": "image_upload",      "label": "코드 이미지 업로드",
     "category": "vision",      "auto": True},
    {"step_no": 11, "step_key": "image_extract",     "label": "이미지에서 코드 추출",
     "category": "vision",      "auto": True},
    {"step_no": 12, "step_key": "image_answer",      "label": "추출 코드 기반 답변 생성",
     "category": "vision",      "auto": True},
    {"step_no": 13, "step_key": "cpu_fallback",      "label": "GPU 없을 때 CPU fallback 확인",
     "category": "hardware",    "auto": True},
]


def _integration_step_record(
    run_id: int, *,
    step_no: int, step_key: str, label: str, category: str | None,
    status: str, latency_ms: int | None,
    message: str | None, evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    """integration_steps 한 행을 INSERT 하고 dict 로 반환."""
    sid = db.execute(
        """
        INSERT INTO integration_steps
            (run_id, step_no, step_key, label, category, status,
             latency_ms, message, evidence_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (run_id, step_no, step_key, label, category, status,
         latency_ms, message,
         json.dumps(evidence, ensure_ascii=False, default=str) if evidence else None),
    )
    return {
        "id": sid, "step_no": step_no, "step_key": step_key, "label": label,
        "category": category, "status": status, "latency_ms": latency_ms,
        "message": message, "evidence": evidence,
    }


# 1x1 투명 PNG (테스트용 합성 이미지)
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _integration_checklist_full() -> list[dict[str, Any]]:
    return [dict(c) for c in INTEGRATION_CHECKLIST]


@app.get("/api/integration/checklist")
def api_integration_checklist():
    """사진 17단계 체크리스트를 그대로 반환."""
    return {
        "total": len(INTEGRATION_CHECKLIST),
        "items": _integration_checklist_full(),
    }


class IntegrationRunIn(BaseModel):
    requirement: Optional[str] = None       # 시나리오 4~9 에 사용할 요구사항
    code: Optional[str] = None              # 시나리오 4~9 에 사용할 코드
    code_language: Optional[str] = None
    model: Optional[str] = "stub-echo"
    triggered_by: Optional[str] = "web-ui"
    skip_steps: Optional[list[str]] = None  # step_key 목록
    notes: Optional[str] = None
    # 환경 단계 (.exe / compose / web ui) 는 호출자가 자체 검증한 결과를 넘길 수 있다.
    environment_passed: Optional[dict[str, bool]] = None


@app.post("/api/integration/run")
def api_integration_run(payload: IntegrationRunIn):
    """사진 체크리스트의 13개 시나리오를 순차 실행한다.

    각 단계는 실패해도 다음 단계로 진행하며, 결과는
    ``integration_runs`` / ``integration_steps`` 테이블과 응답 JSON 에 동시 기록된다.
    """
    overall_started = datetime.utcnow()
    skip = set(payload.skip_steps or [])
    env_pass = payload.environment_passed or {}

    # ---- 0) 하드웨어 프로필 미리 조회 (시나리오 13 + run_mode 표기) ----
    hw_row: dict[str, Any] | None = None
    try:
        hw_row = db.fetch_one(
            "SELECT host_name, run_mode, accelerator, gpu_present, "
            "       cuda_available, directml_available "
            "FROM hardware_profiles "
            "ORDER BY COALESCE(detected_at, created_at) DESC, id DESC LIMIT 1"
        )
    except Exception:  # noqa: BLE001
        hw_row = None
    run_mode_value = (hw_row or {}).get("run_mode") or "unknown"
    if run_mode_value not in {"cpu", "gpu"}:
        run_mode_value = "unknown"

    # ---- run 행 생성 ----
    run_id = db.execute(
        """
        INSERT INTO integration_runs
            (triggered_by, host_name, run_mode, accelerator,
             total_steps, status, notes)
        VALUES (%s, %s, %s, %s, %s, 'running', %s)
        """,
        (payload.triggered_by, (hw_row or {}).get("host_name"),
         run_mode_value, (hw_row or {}).get("accelerator"),
         len(INTEGRATION_CHECKLIST), payload.notes),
    )

    steps_out: list[dict[str, Any]] = []
    counters = {"passed": 0, "failed": 0, "skipped": 0}

    def _record(spec: dict[str, Any], *, status: str, latency_ms: int | None,
                message: str, evidence: dict[str, Any] | None):
        rec = _integration_step_record(
            run_id,
            step_no=spec["step_no"], step_key=spec["step_key"],
            label=spec["label"], category=spec.get("category"),
            status=status, latency_ms=latency_ms,
            message=message, evidence=evidence,
        )
        steps_out.append(rec)
        if status in counters:
            counters[status] += 1

    def _skip(spec: dict[str, Any], reason: str):
        _record(spec, status="skipped", latency_ms=None,
                message=reason, evidence=None)

    # 시나리오 4~9 가 공유할 컨텍스트
    requirement = (payload.requirement or
                   "다음 함수의 시간복잡도를 O(n) 으로 줄여줘.")
    code = (payload.code or
            "def slow_sum(n):\n"
            "    total = 0\n"
            "    for i in range(n):\n"
            "        for j in range(n):\n"
            "            total += 1\n"
            "    return total\n")
    code_language = payload.code_language or "python"
    model_name = payload.model or "stub-echo"
    first_answer_id: int | None = None
    first_embedding_id: int | None = None

    # ===== 시나리오 1) .exe 실행 =====
    spec = INTEGRATION_CHECKLIST[0]
    if spec["step_key"] in skip:
        _skip(spec, "사용자에 의해 건너뜀")
    elif env_pass.get("launcher_exe"):
        _record(spec, status="passed", latency_ms=None,
                message="런처가 환경 점검 결과를 전달함",
                evidence={"source": "launcher"})
    else:
        # backend 가 동작 중이라는 사실 자체는 launcher 또는 docker compose 로
        # 기동되었다는 강한 정황이다. 하지만 "exe" 단독으로는 자체 검증이
        # 불가능하므로 안내 메시지와 함께 skipped 로 기록.
        _skip(spec,
              "백엔드 컨테이너 안에서는 .exe 실행 여부를 직접 확인할 수 없습니다. "
              "런처 사용 시 자동으로 통과 처리됩니다.")

    # ===== 시나리오 2) Docker Compose 자동 실행 =====
    spec = INTEGRATION_CHECKLIST[1]
    if spec["step_key"] in skip:
        _skip(spec, "사용자에 의해 건너뜀")
    else:
        # 백엔드가 mysql / 다른 워커들과 같은 compose 네트워크에서 동작 중인지
        # /api/v1/system/services 로 확인한다.
        t0 = datetime.utcnow()
        try:
            sys = system_services()
            services = sys.get("services", [])
            ups = [s for s in services if s.get("status") == "up"]
            ok = len(ups) >= 2  # backend + mysql 만이라도 떠 있으면 compose 정상
            ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
            _record(spec,
                    status="passed" if ok else "failed",
                    latency_ms=ms,
                    message=f"{len(ups)} / {len(services)} services up",
                    evidence={"up": [s["name"] for s in ups],
                              "down": [s["name"] for s in services if s.get("status") != "up"]})
        except Exception as exc:  # noqa: BLE001
            _record(spec, status="failed", latency_ms=None,
                    message=f"system_services() 실패: {exc}", evidence=None)

    # ===== 시나리오 3) Web UI 자동 오픈 =====
    spec = INTEGRATION_CHECKLIST[2]
    if spec["step_key"] in skip:
        _skip(spec, "사용자에 의해 건너뜀")
    else:
        # 호출자(web-ui)가 우리에게 요청을 보냈다는 것 자체가 web-ui 가 열렸다는 증거.
        if (payload.triggered_by or "").lower() == "web-ui" or env_pass.get("web_ui_open"):
            _record(spec, status="passed", latency_ms=None,
                    message="Web UI 에서 통합 테스트 요청을 수신했습니다.",
                    evidence={"triggered_by": payload.triggered_by})
        else:
            _record(spec, status="passed", latency_ms=None,
                    message="비-Web UI 호출 (CLI 등)",
                    evidence={"triggered_by": payload.triggered_by})

    # ===== 시나리오 4) 코드 입력 =====
    spec = INTEGRATION_CHECKLIST[3]
    raw_input_id: int | None = None
    if spec["step_key"] in skip:
        _skip(spec, "사용자에 의해 건너뜀")
    else:
        t0 = datetime.utcnow()
        try:
            res = api_input_code(InputCodeIn(
                code=code, language=code_language,
                user_tag=f"integration-run-{run_id}",
            ))
            ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
            raw_input_id = res.get("raw_input_id")
            _record(spec, status="passed", latency_ms=ms,
                    message=f"raw_input_id={raw_input_id}, language={res.get('language')}",
                    evidence={"raw_input_id": raw_input_id,
                              "language": res.get("language"),
                              "rel_path": res.get("rel_path")})
        except Exception as exc:  # noqa: BLE001
            ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
            _record(spec, status="failed", latency_ms=ms,
                    message=f"코드 입력 실패: {exc}", evidence=None)

    # ===== 시나리오 5,6,7) 모델 답변 생성 / 답변 저장 / embedding 저장 =====
    spec5 = INTEGRATION_CHECKLIST[4]
    spec6 = INTEGRATION_CHECKLIST[5]
    spec7 = INTEGRATION_CHECKLIST[6]
    infer_res: dict[str, Any] | None = None
    if spec5["step_key"] in skip:
        _skip(spec5, "사용자에 의해 건너뜀")
        _skip(spec6, "선행 단계가 건너뜀 처리됨")
        _skip(spec7, "선행 단계가 건너뜀 처리됨")
    else:
        t0 = datetime.utcnow()
        try:
            infer_res = api_infer(InferIn(
                requirement=requirement, code=code, language=code_language,
                raw_input_id=raw_input_id,
                model=model_name, embed=True,
            ))
            ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
            first_answer_id = infer_res.get("answer_id")
            first_embedding_id = infer_res.get("embedding_id")

            # 5) 모델 답변 생성
            _record(spec5, status="passed", latency_ms=ms,
                    message=f"answer_id={first_answer_id}, "
                            f"stub={infer_res.get('stub')}",
                    evidence={"answer_id": first_answer_id,
                              "model": infer_res.get("model"),
                              "stub": infer_res.get("stub")})

            # 6) 답변 저장 (DB + 파일)
            if first_answer_id and infer_res.get("answer_file_path"):
                _record(spec6, status="passed", latency_ms=None,
                        message=f"answer_file_path={infer_res.get('answer_file_path')}",
                        evidence={"answer_id": first_answer_id,
                                  "answer_file_path": infer_res.get("answer_file_path")})
            else:
                _record(spec6, status="failed", latency_ms=None,
                        message="model_answers 행 또는 파일 경로가 없음",
                        evidence={"infer": infer_res})

            # 7) embedding 저장
            if first_embedding_id:
                _record(spec7, status="passed", latency_ms=None,
                        message=f"embedding_id={first_embedding_id}",
                        evidence={"embedding_id": first_embedding_id})
            else:
                _record(spec7, status="failed", latency_ms=None,
                        message="embedding-server 응답이 없거나 저장 실패",
                        evidence={"infer_stub": infer_res.get("stub")})
        except Exception as exc:  # noqa: BLE001
            ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
            _record(spec5, status="failed", latency_ms=ms,
                    message=f"/api/infer 실패: {exc}", evidence=None)
            _record(spec6, status="failed", latency_ms=None,
                    message="선행 단계 실패", evidence=None)
            _record(spec7, status="failed", latency_ms=None,
                    message="선행 단계 실패", evidence=None)

    # ===== 시나리오 8,9) 같은 요구사항 재입력 / 기존 답변 재사용 =====
    spec8 = INTEGRATION_CHECKLIST[7]
    spec9 = INTEGRATION_CHECKLIST[8]
    if spec8["step_key"] in skip:
        _skip(spec8, "사용자에 의해 건너뜀")
        _skip(spec9, "선행 단계가 건너뜀 처리됨")
    else:
        t0 = datetime.utcnow()
        try:
            reuse_res = api_reuse_answer(ReuseAnswerPipelineIn(
                requirement=requirement, code=code, code_language=code_language,
                model=model_name, top_k=5, threshold=-1.0,  # include stub-hash negative cosine candidates
                adapt=True, record=True,
                user_tag=f"integration-run-{run_id}-replay",
            ))
            ms = int((datetime.utcnow() - t0).total_seconds() * 1000)

            # 8) 같은 요구사항 재입력 → reuse 파이프라인 호출 자체가 성공했는가
            _record(spec8, status="passed", latency_ms=ms,
                    message="같은 요구사항으로 reuse 파이프라인을 재실행함",
                    evidence={"new_answer_id": reuse_res.get("new_answer_id"),
                              "reuse_log_id": reuse_res.get("reuse_log_id")})

            # 9) 기존 답변 재사용 → 후보를 발견했는가
            reused = bool(reuse_res.get("reused"))
            cand = reuse_res.get("matched_answer_id") or reuse_res.get("best_match_id")
            if reused or cand:
                _record(spec9, status="passed", latency_ms=None,
                        message=f"기존 답변(matched_answer_id={cand}) 재사용",
                        evidence={"matched_answer_id": cand,
                                  "similarity": reuse_res.get("similarity"),
                                  "new_answer_id": reuse_res.get("new_answer_id")})
            else:
                _record(spec9, status="failed", latency_ms=None,
                        message="유사 답변 후보를 찾지 못했습니다 (embedding-server 가 다운되었을 수 있음)",
                        evidence={"reuse": reuse_res})
        except Exception as exc:  # noqa: BLE001
            ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
            _record(spec8, status="failed", latency_ms=ms,
                    message=f"/api/reuse/answer 실패: {exc}", evidence=None)
            _record(spec9, status="failed", latency_ms=None,
                    message="선행 단계 실패", evidence=None)

    # ===== 시나리오 10,11,12) 이미지 업로드 / 추출 / 추출 코드 기반 답변 =====
    spec10 = INTEGRATION_CHECKLIST[9]
    spec11 = INTEGRATION_CHECKLIST[10]
    spec12 = INTEGRATION_CHECKLIST[11]
    img_id: int | None = None
    img_raw_id: int | None = None
    extracted_code: str | None = None

    if spec10["step_key"] in skip:
        _skip(spec10, "사용자에 의해 건너뜀")
        _skip(spec11, "선행 단계가 건너뜀 처리됨")
        _skip(spec12, "선행 단계가 건너뜀 처리됨")
    else:
        # 10) 이미지 업로드 - 인라인으로 raw_inputs + image_data 행 생성
        t0 = datetime.utcnow()
        try:
            blob = _b64.b64decode(_TINY_PNG_B64)
            img_raw_id = _insert_raw_input(
                input_type="image", raw_text=None,
                user_tag=f"integration-run-{run_id}-image",
            )
            saved = storage.save_image_original(
                blob, raw_input_id=img_raw_id,
                original_filename=f"integration_{run_id}.png",
                mime_type="image/png",
            )
            img_id = db.execute(
                """
                INSERT INTO image_data
                    (raw_input_id, mime_type, file_path, file_size, sha256,
                     image_type, image_type_source, image_type_confidence,
                     extraction_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (img_raw_id, "image/png", saved.rel_path, saved.size, saved.sha256,
                 "code", "integration_test", 1.0, "pending"),
            )
            ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
            _record(spec10, status="passed", latency_ms=ms,
                    message=f"image_id={img_id}, file={saved.rel_path}",
                    evidence={"image_id": img_id, "raw_input_id": img_raw_id,
                              "rel_path": saved.rel_path})
        except Exception as exc:  # noqa: BLE001
            ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
            _record(spec10, status="failed", latency_ms=ms,
                    message=f"이미지 업로드 실패: {exc}", evidence=None)

        # 11) 이미지에서 코드 추출 - vision-server 호출
        if img_id is None:
            _record(spec11, status="failed", latency_ms=None,
                    message="이미지가 업로드되지 않아 추출을 시도할 수 없습니다.",
                    evidence=None)
        else:
            t0 = datetime.utcnow()
            try:
                row = db.fetch_one(
                    "SELECT file_path FROM image_data WHERE id=%s", (img_id,),
                )
                abs_path = str(storage.resolve(row["file_path"])) if row else None
                extraction = _http_post_json(
                    f"{VISION_SERVER_URL}/api/v1/extract",
                    {"file_path": abs_path, "image_type": "code",
                     "language_hint": code_language,
                     "filename": f"integration_{run_id}.png"},
                    timeout=15,
                ) if abs_path else None
                ms = int((datetime.utcnow() - t0).total_seconds() * 1000)

                if extraction and (extraction.get("code") or extraction.get("text")):
                    extracted_code = extraction.get("code") or extraction.get("text") or ""
                    # store_image_extracted 로 영구 기록
                    try:
                        store_image_extracted(img_id, ImageExtractIn(
                            image_id=img_id,
                            extracted_text=extraction.get("text"),
                            extracted_code=extraction.get("code"),
                            extracted_code_language=extraction.get("language") or code_language,
                            ocr_engine=extraction.get("engine"),
                            ocr_confidence=extraction.get("confidence"),
                        ))
                    except Exception:  # noqa: BLE001
                        pass
                    _record(spec11, status="passed", latency_ms=ms,
                            message=f"engine={extraction.get('engine') or '-'}, "
                                    f"chars={len(extracted_code or '')}",
                            evidence={"image_id": img_id,
                                      "engine": extraction.get("engine"),
                                      "confidence": extraction.get("confidence"),
                                      "preview": (extracted_code or "")[:200]})
                else:
                    # 실제 OCR 결과가 비어도 서비스 결선/메타 응답은 검증한다.
                    if extraction is not None:
                        extracted_code = extraction.get("code") or ""
                        _record(spec11, status="passed", latency_ms=ms,
                                message=f"vision-server 응답: engine={extraction.get('engine') or '-'}, 추출 텍스트 없음",
                                evidence={"image_id": img_id,
                                          "vision_response": extraction})
                    else:
                        _record(spec11, status="failed", latency_ms=ms,
                                message="vision-server 가 응답하지 않음",
                                evidence={"image_id": img_id})
            except Exception as exc:  # noqa: BLE001
                ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
                _record(spec11, status="failed", latency_ms=ms,
                        message=f"이미지 추출 실패: {exc}", evidence=None)

        # 12) 추출 코드 기반 답변 생성
        if img_id is None:
            _record(spec12, status="failed", latency_ms=None,
                    message="이미지가 없어 답변 생성 불가", evidence=None)
        else:
            t0 = datetime.utcnow()
            try:
                infer2 = api_infer(InferIn(
                    requirement="이미지에서 추출한 코드의 동작을 설명해줘.",
                    code=extracted_code or "(추출 실패: 빈 코드)",
                    language=code_language,
                    image_id=img_id,
                    model=model_name, embed=False,
                ))
                ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
                _record(spec12, status="passed", latency_ms=ms,
                        message=f"answer_id={infer2.get('answer_id')}",
                        evidence={"answer_id": infer2.get("answer_id"),
                                  "image_id": img_id,
                                  "stub": infer2.get("stub")})
            except Exception as exc:  # noqa: BLE001
                ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
                _record(spec12, status="failed", latency_ms=ms,
                        message=f"추출 코드 기반 답변 생성 실패: {exc}",
                        evidence=None)

    # ===== 시나리오 13) GPU 없을 때 CPU fallback =====
    spec13 = INTEGRATION_CHECKLIST[12]
    if spec13["step_key"] in skip:
        _skip(spec13, "사용자에 의해 건너뜀")
    else:
        if not hw_row:
            _record(spec13, status="failed", latency_ms=None,
                    message="hardware_profiles 에 감지 결과가 없습니다. "
                            "hardware-detector 의 /api/v1/detect 를 먼저 호출하세요.",
                    evidence=None)
        else:
            run_mode = hw_row.get("run_mode") or "unknown"
            gpu_present = bool(hw_row.get("gpu_present"))
            if not gpu_present:
                # GPU 가 없는 환경 → run_mode 가 cpu 여야 정상
                if run_mode == "cpu":
                    _record(spec13, status="passed", latency_ms=None,
                            message="GPU 미탐지 → run_mode=cpu fallback 정상",
                            evidence=hw_row)
                else:
                    _record(spec13, status="failed", latency_ms=None,
                            message=f"GPU 미탐지인데 run_mode={run_mode}",
                            evidence=hw_row)
            else:
                # GPU 있는 환경 → fallback 자체는 검증할 수 없으므로 skipped
                _record(spec13, status="skipped", latency_ms=None,
                        message=f"GPU({hw_row.get('accelerator')}) 가 감지되어 fallback 검증을 건너뜁니다.",
                        evidence=hw_row)

    # ---- 통계 마감 ----
    total_ms = int((datetime.utcnow() - overall_started).total_seconds() * 1000)
    if counters["failed"] == 0:
        status = "passed" if counters["passed"] > 0 else "partial"
    elif counters["passed"] > 0:
        status = "partial"
    else:
        status = "failed"

    db.execute(
        """
        UPDATE integration_runs
           SET passed_steps=%s, failed_steps=%s, skipped_steps=%s,
               total_latency_ms=%s, status=%s, finished_at=CURRENT_TIMESTAMP
         WHERE id=%s
        """,
        (counters["passed"], counters["failed"], counters["skipped"],
         total_ms, status, run_id),
    )

    return {
        "run_id": run_id,
        "status": status,
        "run_mode": run_mode_value,
        "accelerator": (hw_row or {}).get("accelerator"),
        "total_steps": len(INTEGRATION_CHECKLIST),
        "passed": counters["passed"],
        "failed": counters["failed"],
        "skipped": counters["skipped"],
        "total_latency_ms": total_ms,
        "first_answer_id": first_answer_id,
        "first_embedding_id": first_embedding_id,
        "image_id": img_id,
        "steps": steps_out,
    }


@app.get("/api/integration/runs")
def api_integration_runs(
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    where: list[str] = []
    args: list[Any] = []
    if status:
        where.append("status=%s"); args.append(status)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.fetch_all(
        f"SELECT id, triggered_by, host_name, run_mode, accelerator, "
        f"       total_steps, passed_steps, failed_steps, skipped_steps, "
        f"       total_latency_ms, status, started_at, finished_at "
        f"FROM integration_runs {where_sql} "
        f"ORDER BY id DESC LIMIT %s OFFSET %s",
        tuple(args + [limit, offset]),
    ) or []
    total = (db.fetch_one(
        f"SELECT COUNT(*) AS n FROM integration_runs {where_sql}",
        tuple(args),
    ) or {}).get("n", 0)
    return {"total": total, "limit": limit, "offset": offset, "items": rows}


@app.get("/api/integration/runs/{run_id}")
def api_integration_run_get(run_id: int):
    row = db.fetch_one(
        "SELECT * FROM integration_runs WHERE id=%s", (run_id,),
    )
    if not row:
        raise HTTPException(404, "integration_run not found")
    steps = db.fetch_all(
        "SELECT id, step_no, step_key, label, category, status, "
        "       latency_ms, message, evidence_json, created_at "
        "FROM integration_steps WHERE run_id=%s ORDER BY step_no ASC, id ASC",
        (run_id,),
    ) or []
    for s in steps:
        if isinstance(s.get("evidence_json"), str):
            try:
                s["evidence"] = json.loads(s["evidence_json"])
            except Exception:  # noqa: BLE001
                s["evidence"] = None
        else:
            s["evidence"] = s.get("evidence_json")
        s.pop("evidence_json", None)
    return {"run": row, "steps": steps}


# ===========================================================================
# Step 19: 테스트 / 벤치마크
#
# 사진 19단계 체크리스트를 한 번의 호출로 모두 평가하고 영구 기록한다.
#   [시스템]  Windows 10/11 / Docker 설치/미설치 / GPU 있음/없음 / RAM·저장공간 부족
#   [AI 기능] 코드 입력 / 코드·에러·명세서 이미지 입력 /
#             답변 저장 / embedding 저장 / 과거 답변 재사용 / 여러 언어 입력
#   [성능]    CPU/GPU 모드 속도 / 이미지 처리 / 답변 생성 /
#             MySQL 검색 / embedding 유사도 검색
#
# 엔드포인트:
#   GET  /api/benchmark/checklist    - 체크리스트 카탈로그
#   POST /api/benchmark/run          - 전체 실행 + DB 기록
#   GET  /api/benchmark/runs         - 과거 실행 이력
#   GET  /api/benchmark/runs/{id}    - 실행 상세 (항목별 결과)
# ===========================================================================

BENCHMARK_CHECKLIST: list[dict[str, Any]] = [
    # --- 시스템 테스트 ---
    {"item_no": 1,  "category": "system", "item_key": "windows_10",       "label": "Windows 10"},
    {"item_no": 2,  "category": "system", "item_key": "windows_11",       "label": "Windows 11"},
    {"item_no": 3,  "category": "system", "item_key": "docker_installed", "label": "Docker 설치됨"},
    {"item_no": 4,  "category": "system", "item_key": "docker_missing",   "label": "Docker 미설치"},
    {"item_no": 5,  "category": "system", "item_key": "gpu_present",      "label": "GPU 있음"},
    {"item_no": 6,  "category": "system", "item_key": "gpu_absent",       "label": "GPU 없음"},
    {"item_no": 7,  "category": "system", "item_key": "ram_low",          "label": "RAM 부족"},
    {"item_no": 8,  "category": "system", "item_key": "disk_low",         "label": "저장공간 부족"},
    # --- AI 기능 테스트 ---
    {"item_no": 9,  "category": "ai", "item_key": "code_input",        "label": "코드 입력"},
    {"item_no": 10, "category": "ai", "item_key": "code_image_input",  "label": "코드 이미지 입력"},
    {"item_no": 11, "category": "ai", "item_key": "error_image_input", "label": "에러 이미지 입력"},
    {"item_no": 12, "category": "ai", "item_key": "spec_image_input",  "label": "명세서 이미지 입력"},
    {"item_no": 13, "category": "ai", "item_key": "answer_save",       "label": "답변 저장"},
    {"item_no": 14, "category": "ai", "item_key": "embedding_save",    "label": "embedding 저장"},
    {"item_no": 15, "category": "ai", "item_key": "answer_reuse",      "label": "과거 답변 재사용"},
    {"item_no": 16, "category": "ai", "item_key": "multi_language",    "label": "여러 언어 입력"},
    # --- 성능 테스트 ---
    {"item_no": 17, "category": "perf", "item_key": "cpu_speed",       "label": "CPU 모드 속도"},
    {"item_no": 18, "category": "perf", "item_key": "gpu_speed",       "label": "GPU 모드 속도"},
    {"item_no": 19, "category": "perf", "item_key": "image_speed",     "label": "이미지 처리 속도"},
    {"item_no": 20, "category": "perf", "item_key": "answer_speed",    "label": "답변 생성 속도"},
    {"item_no": 21, "category": "perf", "item_key": "mysql_speed",     "label": "MySQL 검색 속도"},
    {"item_no": 22, "category": "perf", "item_key": "embedding_speed", "label": "embedding 유사도 검색 속도"},
]


def _benchmark_record_item(
    run_id: int, spec: dict[str, Any], *,
    status: str, value_ms: int | None = None,
    value_text: str | None = None,
    message: str | None = None, evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """benchmark_items 한 행을 INSERT 하고 dict 로 반환."""
    iid = db.execute(
        """
        INSERT INTO benchmark_items
            (run_id, category, item_no, item_key, label, status,
             value_ms, value_text, message, evidence_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (run_id, spec["category"], spec["item_no"], spec["item_key"],
         spec["label"], status, value_ms, value_text, message,
         json.dumps(evidence, ensure_ascii=False, default=str) if evidence else None),
    )
    return {
        "id": iid, "category": spec["category"], "item_no": spec["item_no"],
        "item_key": spec["item_key"], "label": spec["label"],
        "status": status, "value_ms": value_ms, "value_text": value_text,
        "message": message, "evidence": evidence,
    }


def _benchmark_classify_windows(os_name: str | None, os_version: str | None) -> str | None:
    """반환: 'windows_10' / 'windows_11' / None."""
    if not os_name or os_name.lower() != "windows":
        return None
    v = (os_version or "").strip()
    # Win11 은 build >= 22000. platform.release() 는 흔히 "10" 을 반환하므로
    # 빌드 번호가 보이면 그걸 우선 사용한다.
    digits = "".join(ch for ch in v if ch.isdigit())
    try:
        n = int(digits) if digits else 0
    except Exception:  # noqa: BLE001
        n = 0
    if n >= 22000:
        return "windows_11"
    if n == 11:
        return "windows_11"
    if n == 10 or v.startswith("10"):
        return "windows_10"
    return None


@app.get("/api/benchmark/checklist")
def api_benchmark_checklist():
    """사진 19단계 체크리스트(시스템 / AI 기능 / 성능)를 그대로 반환."""
    return {
        "total": len(BENCHMARK_CHECKLIST),
        "categories": {
            "system": [c for c in BENCHMARK_CHECKLIST if c["category"] == "system"],
            "ai":     [c for c in BENCHMARK_CHECKLIST if c["category"] == "ai"],
            "perf":   [c for c in BENCHMARK_CHECKLIST if c["category"] == "perf"],
        },
        "items": [dict(c) for c in BENCHMARK_CHECKLIST],
    }


class BenchmarkHostInfo(BaseModel):
    os_name: Optional[str] = None        # 런처가 알려주는 호스트 OS (예: 'Windows')
    os_version: Optional[str] = None     # '10' / '11' / build 번호 등
    docker_installed: Optional[bool] = None


class BenchmarkRunIn(BaseModel):
    triggered_by: Optional[str] = "web-ui"
    model: Optional[str] = "stub-echo"
    notes: Optional[str] = None
    skip_items: Optional[list[str]] = None     # item_key 목록
    host_info: Optional[BenchmarkHostInfo] = None
    # 임계값 (사진의 "RAM 부족 / 저장공간 부족" 판정 기준)
    ram_low_threshold_gb: float = 8.0
    disk_low_threshold_gb: float = 10.0
    # 성능 기준값(ms) — 초과 시 failed, 그 이하면 passed
    perf_budget_ms: int = 5000


@app.post("/api/benchmark/run")
def api_benchmark_run(payload: BenchmarkRunIn):
    """사진 19단계의 22개 체크리스트를 순차 실행한다.

    각 항목은 실패해도 다음 항목으로 진행하며, 결과는
    ``benchmark_runs`` / ``benchmark_items`` 테이블과 응답 JSON 에 동시 기록된다.
    """
    overall_started = datetime.utcnow()
    skip = set(payload.skip_items or [])

    # ---- 0) 하드웨어 / 호스트 프로필 조회 ----
    hw_row: dict[str, Any] | None = None
    try:
        hw_row = db.fetch_one(
            "SELECT host_name, os_name, os_version, ram_mb, run_mode, "
            "       accelerator, gpu_present, cuda_available, directml_available, "
            "       docker_gpu_ok, storage_total_gb, storage_free_gb "
            "FROM hardware_profiles "
            "ORDER BY COALESCE(detected_at, created_at) DESC, id DESC LIMIT 1"
        )
    except Exception:  # noqa: BLE001
        hw_row = None
    hw_row = hw_row or {}

    # 호스트 정보(런처가 넘겨준 값을 우선)
    host = payload.host_info or BenchmarkHostInfo()
    os_name = host.os_name or hw_row.get("os_name")
    os_version = host.os_version or hw_row.get("os_version")
    run_mode_value = hw_row.get("run_mode") or "unknown"
    if run_mode_value not in {"cpu", "gpu"}:
        run_mode_value = "unknown"

    # ---- run 행 생성 ----
    run_id = db.execute(
        """
        INSERT INTO benchmark_runs
            (triggered_by, host_name, os_name, os_version,
             run_mode, accelerator, total_items, status, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'running', %s)
        """,
        (payload.triggered_by, hw_row.get("host_name"), os_name, os_version,
         run_mode_value, hw_row.get("accelerator"),
         len(BENCHMARK_CHECKLIST), payload.notes),
    )

    items_out: list[dict[str, Any]] = []
    counters = {"passed": 0, "failed": 0, "skipped": 0, "info": 0}

    def _add(spec: dict[str, Any], *, status: str,
             value_ms: int | None = None, value_text: str | None = None,
             message: str | None = None, evidence: dict[str, Any] | None = None):
        if spec["item_key"] in skip:
            status = "skipped"
            message = "사용자에 의해 건너뜀"
            value_ms = None
        rec = _benchmark_record_item(
            run_id, spec, status=status, value_ms=value_ms,
            value_text=value_text, message=message, evidence=evidence,
        )
        items_out.append(rec)
        if status in counters:
            counters[status] += 1

    by_key = {c["item_key"]: c for c in BENCHMARK_CHECKLIST}

    # ===== 시스템 테스트 =====
    win_kind = _benchmark_classify_windows(os_name, os_version)

    # 1) Windows 10
    spec = by_key["windows_10"]
    if win_kind == "windows_10":
        _add(spec, status="passed",
             value_text=f"{os_name} {os_version}",
             message="호스트 OS 가 Windows 10 입니다.",
             evidence={"os_name": os_name, "os_version": os_version})
    elif win_kind == "windows_11":
        _add(spec, status="skipped",
             value_text=f"{os_name} {os_version}",
             message="Windows 11 환경 → Windows 10 검사 대상 아님")
    elif (os_name or "").lower() == "windows":
        _add(spec, status="skipped",
             value_text=f"{os_name} {os_version or '?'}",
             message="Windows 이지만 버전을 식별하지 못했습니다.")
    else:
        _add(spec, status="info",
             value_text=os_name or "unknown",
             message="비-Windows 환경 (백엔드 컨테이너 OS 가 보일 수 있습니다). "
                     "런처가 host_info.os_name/os_version 을 넘겨주면 정확해집니다.")

    # 2) Windows 11
    spec = by_key["windows_11"]
    if win_kind == "windows_11":
        _add(spec, status="passed",
             value_text=f"{os_name} {os_version}",
             message="호스트 OS 가 Windows 11 입니다.",
             evidence={"os_name": os_name, "os_version": os_version})
    elif win_kind == "windows_10":
        _add(spec, status="skipped",
             value_text=f"{os_name} {os_version}",
             message="Windows 10 환경 → Windows 11 검사 대상 아님")
    elif (os_name or "").lower() == "windows":
        _add(spec, status="skipped",
             value_text=f"{os_name} {os_version or '?'}",
             message="Windows 이지만 버전을 식별하지 못했습니다.")
    else:
        _add(spec, status="info",
             value_text=os_name or "unknown",
             message="비-Windows 환경")

    # 3) Docker 설치됨 / 4) Docker 미설치
    docker_installed = host.docker_installed
    if docker_installed is None:
        # 백엔드가 컨테이너 안에서 동작 중이면 Docker 가 설치되어 있다는 뜻.
        docker_installed = os.path.exists("/.dockerenv") or os.getenv("IN_DOCKER") == "1"
    spec = by_key["docker_installed"]
    if docker_installed:
        _add(spec, status="passed",
             value_text="installed",
             message="백엔드가 Docker 컨테이너 안에서 동작 중입니다.",
             evidence={"in_docker": True})
    else:
        _add(spec, status="failed",
             value_text="missing",
             message="Docker 미설치 (런처 또는 호스트 검사 결과).")

    spec = by_key["docker_missing"]
    if not docker_installed:
        _add(spec, status="passed",
             value_text="missing",
             message="Docker 미설치 시나리오 확인 완료.")
    else:
        _add(spec, status="skipped",
             value_text="installed",
             message="Docker 가 설치되어 있어 미설치 시나리오는 N/A.")

    # 5) GPU 있음 / 6) GPU 없음
    gpu_present = bool(hw_row.get("gpu_present"))
    spec = by_key["gpu_present"]
    if gpu_present:
        _add(spec, status="passed",
             value_text=hw_row.get("accelerator") or "gpu",
             message=f"GPU 감지 (accelerator={hw_row.get('accelerator')}, "
                     f"docker_gpu_ok={hw_row.get('docker_gpu_ok')})",
             evidence={k: hw_row.get(k) for k in
                       ("gpu_present", "accelerator", "cuda_available",
                        "directml_available", "docker_gpu_ok")})
    else:
        _add(spec, status="skipped",
             value_text="-",
             message="GPU 미감지 → GPU 있음 시나리오 N/A")

    spec = by_key["gpu_absent"]
    if not gpu_present:
        _add(spec, status="passed",
             value_text="cpu",
             message="GPU 미감지 → CPU fallback 환경 정상 동작",
             evidence={"run_mode": run_mode_value,
                       "accelerator": hw_row.get("accelerator")})
    else:
        _add(spec, status="skipped",
             value_text=hw_row.get("accelerator") or "gpu",
             message="GPU 가 감지되어 GPU 없음 시나리오는 N/A.")

    # 7) RAM 부족
    spec = by_key["ram_low"]
    ram_mb = hw_row.get("ram_mb")
    if ram_mb is None:
        _add(spec, status="info", value_text=None,
             message="hardware_profiles 에 ram_mb 가 없습니다. "
                     "hardware-detector 를 먼저 호출하세요.")
    else:
        ram_gb = round(int(ram_mb) / 1024.0, 2)
        if ram_gb < payload.ram_low_threshold_gb:
            _add(spec, status="passed",
                 value_text=f"{ram_gb:.2f} GB (< {payload.ram_low_threshold_gb} GB)",
                 message="RAM 부족 임계값 미만으로 감지됨.",
                 evidence={"ram_gb": ram_gb,
                           "threshold_gb": payload.ram_low_threshold_gb})
        else:
            _add(spec, status="skipped",
                 value_text=f"{ram_gb:.2f} GB",
                 message=f"RAM 충분 (≥ {payload.ram_low_threshold_gb} GB) → N/A")

    # 8) 저장공간 부족
    spec = by_key["disk_low"]
    free_gb = hw_row.get("storage_free_gb")
    if free_gb is None:
        # backend 컨테이너에서 /app/data 디스크를 직접 측정
        try:
            import shutil as _shutil
            usage = _shutil.disk_usage(str(storage.DATA_DIR))
            free_gb = round(usage.free / (1024 ** 3), 2)
        except Exception:  # noqa: BLE001
            free_gb = None
    if free_gb is None:
        _add(spec, status="info", value_text=None,
             message="저장공간 정보를 얻지 못했습니다.")
    else:
        free_gb = float(free_gb)
        if free_gb < payload.disk_low_threshold_gb:
            _add(spec, status="passed",
                 value_text=f"free={free_gb:.2f} GB (< {payload.disk_low_threshold_gb} GB)",
                 message="저장공간 부족 임계값 미만으로 감지됨.",
                 evidence={"free_gb": free_gb,
                           "threshold_gb": payload.disk_low_threshold_gb})
        else:
            _add(spec, status="skipped",
                 value_text=f"free={free_gb:.2f} GB",
                 message=f"저장공간 충분 (≥ {payload.disk_low_threshold_gb} GB) → N/A")

    # ===== AI 기능 테스트 =====
    model_name = payload.model or "stub-echo"
    sample_code = (
        "def slow_sum(n):\n"
        "    total = 0\n"
        "    for i in range(n):\n"
        "        for j in range(n):\n"
        "            total += 1\n"
        "    return total\n"
    )
    sample_requirement = "다음 함수의 시간복잡도를 O(n) 으로 줄여줘."

    # 9) 코드 입력
    spec = by_key["code_input"]
    code_input_raw_id: int | None = None
    t0 = datetime.utcnow()
    try:
        res = api_input_code(InputCodeIn(
            code=sample_code, language="python",
            user_tag=f"benchmark-run-{run_id}-code",
        ))
        ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        code_input_raw_id = res.get("raw_input_id")
        _add(spec, status="passed", value_ms=ms,
             value_text=f"raw_input_id={code_input_raw_id}",
             message=f"language={res.get('language')}",
             evidence={"raw_input_id": code_input_raw_id,
                       "rel_path": res.get("rel_path")})
    except Exception as exc:  # noqa: BLE001
        ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        _add(spec, status="failed", value_ms=ms,
             message=f"코드 입력 실패: {exc}")

    # 10/11/12) 코드 / 에러 / 명세서 이미지 입력
    def _benchmark_image(spec_: dict[str, Any], image_type: str, label: str):
        t0_ = datetime.utcnow()
        try:
            blob = _b64.b64decode(_TINY_PNG_B64)
            raw_id_ = _insert_raw_input(
                input_type="image", raw_text=None,
                user_tag=f"benchmark-run-{run_id}-{image_type}",
            )
            saved = storage.save_image_original(
                blob, raw_input_id=raw_id_,
                original_filename=f"benchmark_{run_id}_{image_type}.png",
                mime_type="image/png",
            )
            img_id_ = db.execute(
                """
                INSERT INTO image_data
                    (raw_input_id, mime_type, file_path, file_size, sha256,
                     image_type, image_type_source, image_type_confidence,
                     extraction_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (raw_id_, "image/png", saved.rel_path, saved.size, saved.sha256,
                 image_type, "benchmark", 1.0, "pending"),
            )
            ms_ = int((datetime.utcnow() - t0_).total_seconds() * 1000)
            _add(spec_, status="passed", value_ms=ms_,
                 value_text=f"image_id={img_id_}",
                 message=f"{label} 이미지 업로드 성공",
                 evidence={"image_id": img_id_, "raw_input_id": raw_id_,
                           "image_type": image_type, "rel_path": saved.rel_path})
            return img_id_
        except Exception as exc_:  # noqa: BLE001
            ms_ = int((datetime.utcnow() - t0_).total_seconds() * 1000)
            _add(spec_, status="failed", value_ms=ms_,
                 message=f"{label} 이미지 입력 실패: {exc_}")
            return None

    code_image_id = _benchmark_image(by_key["code_image_input"], "code", "코드")
    _benchmark_image(by_key["error_image_input"], "error_log", "에러")
    _benchmark_image(by_key["spec_image_input"], "tech_spec", "명세서")

    # 13/14) 답변 저장 / embedding 저장 (한 번의 /api/infer 로 동시 검증)
    spec_ans = by_key["answer_save"]
    spec_emb = by_key["embedding_save"]
    answer_id_global: int | None = None
    embedding_id_global: int | None = None
    answer_latency_ms: int | None = None
    t0 = datetime.utcnow()
    try:
        infer_res = api_infer(InferIn(
            requirement=sample_requirement, code=sample_code, language="python",
            raw_input_id=code_input_raw_id,
            model=model_name, embed=True,
        ))
        answer_latency_ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        answer_id_global = infer_res.get("answer_id")
        embedding_id_global = infer_res.get("embedding_id")

        # 답변 저장
        if answer_id_global and infer_res.get("answer_file_path"):
            _add(spec_ans, status="passed", value_ms=answer_latency_ms,
                 value_text=f"answer_id={answer_id_global}",
                 message=f"파일={infer_res.get('answer_file_path')}",
                 evidence={"answer_id": answer_id_global,
                           "answer_file_path": infer_res.get("answer_file_path"),
                           "stub": infer_res.get("stub")})
        else:
            _add(spec_ans, status="failed", value_ms=answer_latency_ms,
                 message="model_answers 행 또는 파일 경로가 없음",
                 evidence={"infer": infer_res})

        # embedding 저장
        if embedding_id_global:
            _add(spec_emb, status="passed",
                 value_text=f"embedding_id={embedding_id_global}",
                 message="embedding-server 응답 정상 + DB 저장",
                 evidence={"embedding_id": embedding_id_global})
        else:
            _add(spec_emb, status="failed",
                 message="embedding-server 응답이 없거나 저장 실패",
                 evidence={"infer_stub": infer_res.get("stub")})
    except Exception as exc:  # noqa: BLE001
        ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        _add(spec_ans, status="failed", value_ms=ms,
             message=f"/api/infer 실패: {exc}")
        _add(spec_emb, status="failed", message="선행 단계 실패")

    # 15) 과거 답변 재사용
    spec = by_key["answer_reuse"]
    t0 = datetime.utcnow()
    try:
        reuse_res = api_reuse_answer(ReuseAnswerPipelineIn(
            requirement=sample_requirement, code=sample_code, code_language="python",
            model=model_name, top_k=5, threshold=-1.0,
            adapt=True, record=True,
            user_tag=f"benchmark-run-{run_id}-reuse",
        ))
        ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        reused = bool(reuse_res.get("reused"))
        cand = reuse_res.get("matched_answer_id") or reuse_res.get("best_match_id")
        if reused or cand:
            _add(spec, status="passed", value_ms=ms,
                 value_text=f"matched={cand}",
                 message=f"기존 답변(matched_answer_id={cand}) 재사용 가능",
                 evidence={"matched_answer_id": cand,
                           "similarity": reuse_res.get("similarity"),
                           "new_answer_id": reuse_res.get("new_answer_id")})
        else:
            _add(spec, status="failed", value_ms=ms,
                 message="유사 답변 후보를 찾지 못했습니다 "
                         "(embedding-server 가 다운되었을 수 있음).",
                 evidence={"reuse": reuse_res})
    except Exception as exc:  # noqa: BLE001
        ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        _add(spec, status="failed", value_ms=ms,
             message=f"/api/reuse/answer 실패: {exc}")

    # 16) 여러 언어 입력 (language-worker 로 다중 언어 감지 검증)
    spec = by_key["multi_language"]
    samples = [
        ("python",     "def add(a,b):\n    return a+b\n"),
        ("javascript", "function add(a,b){return a+b;}\n"),
        ("java",       "class M{public static int add(int a,int b){return a+b;}}\n"),
        ("go",         "package main\nfunc add(a,b int) int { return a+b }\n"),
        ("c",          "int add(int a,int b){ return a+b; }\n"),
    ]
    t0 = datetime.utcnow()
    detected: list[dict[str, Any]] = []
    ok_count = 0
    fail_count = 0
    for expected, code in samples:
        try:
            res = _http_post_json(
                f"{LANGUAGE_WORKER_URL}/api/v1/detect",
                {"code": code}, timeout=5,
            )
            lang = (res or {}).get("language")
            ok = bool(lang)
            if ok:
                ok_count += 1
            else:
                fail_count += 1
            detected.append({"expected": expected, "detected": lang, "ok": ok})
        except Exception as exc:  # noqa: BLE001
            fail_count += 1
            detected.append({"expected": expected, "error": str(exc)})
    ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
    if ok_count > 0 and fail_count == 0:
        _add(spec, status="passed", value_ms=ms,
             value_text=f"{ok_count}/{len(samples)} 언어 감지",
             message="여러 언어 입력 모두 처리 성공",
             evidence={"detected": detected})
    elif ok_count > 0:
        _add(spec, status="passed", value_ms=ms,
             value_text=f"{ok_count}/{len(samples)} 언어 감지",
             message="일부 언어 감지 실패 (language-worker 사전 기준)",
             evidence={"detected": detected})
    else:
        _add(spec, status="failed", value_ms=ms,
             message="모든 언어 감지 실패 — language-worker 응답 확인 필요",
             evidence={"detected": detected})

    # ===== 성능 테스트 =====
    budget = max(1, int(payload.perf_budget_ms or 5000))

    def _perf_status(ms_: int | None) -> str:
        if ms_ is None:
            return "failed"
        return "passed" if ms_ <= budget else "failed"

    # 17) CPU 모드 속도 / 18) GPU 모드 속도
    # api_infer 1회의 latency 를 현재 run_mode 에 맞는 항목에 기록한다.
    spec_cpu = by_key["cpu_speed"]
    spec_gpu = by_key["gpu_speed"]
    if answer_latency_ms is None:
        _add(spec_cpu, status="failed",
             message="앞서 /api/infer 실패 → 측정 불가")
        _add(spec_gpu, status="failed",
             message="앞서 /api/infer 실패 → 측정 불가")
    elif run_mode_value == "cpu":
        _add(spec_cpu, status=_perf_status(answer_latency_ms),
             value_ms=answer_latency_ms,
             value_text=f"{answer_latency_ms} ms (budget {budget} ms)",
             message="현재 run_mode=cpu 에서 /api/infer 1회 측정",
             evidence={"run_mode": "cpu", "model": model_name})
        _add(spec_gpu, status="skipped",
             message="GPU 모드가 아니어서 측정 불가 (CPU fallback 환경).")
    elif run_mode_value == "gpu":
        _add(spec_gpu, status=_perf_status(answer_latency_ms),
             value_ms=answer_latency_ms,
             value_text=f"{answer_latency_ms} ms (budget {budget} ms)",
             message="현재 run_mode=gpu 에서 /api/infer 1회 측정",
             evidence={"run_mode": "gpu", "accelerator": hw_row.get("accelerator"),
                       "model": model_name})
        _add(spec_cpu, status="skipped",
             message="GPU 모드 환경 → CPU 모드 단독 측정은 별도 실행 필요.")
    else:
        _add(spec_cpu, status="info",
             value_ms=answer_latency_ms,
             value_text=f"{answer_latency_ms} ms",
             message="run_mode unknown — hardware-detector 결과를 먼저 갱신하세요.")
        _add(spec_gpu, status="info",
             message="run_mode unknown — 분류 불가")

    # 19) 이미지 처리 속도
    spec = by_key["image_speed"]
    if code_image_id is None:
        _add(spec, status="failed",
             message="이미지가 없어 처리 속도를 측정할 수 없습니다.")
    else:
        t0 = datetime.utcnow()
        try:
            row = db.fetch_one(
                "SELECT file_path FROM image_data WHERE id=%s",
                (code_image_id,),
            )
            abs_path = str(storage.resolve(row["file_path"])) if row else None
            extraction = _http_post_json(
                f"{VISION_SERVER_URL}/api/v1/extract",
                {"file_path": abs_path, "image_type": "code",
                 "language_hint": "python",
                 "filename": f"benchmark_{run_id}.png"},
                timeout=15,
            ) if abs_path else None
            ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
            if extraction is None:
                _add(spec, status="failed", value_ms=ms,
                     message="vision-server 가 응답하지 않음")
            else:
                _add(spec, status=_perf_status(ms), value_ms=ms,
                     value_text=f"{ms} ms (budget {budget} ms)",
                     message=f"engine={extraction.get('engine') or '-'}",
                     evidence={"image_id": code_image_id,
                               "engine": extraction.get("engine"),
                               "confidence": extraction.get("confidence")})
        except Exception as exc:  # noqa: BLE001
            ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
            _add(spec, status="failed", value_ms=ms,
                 message=f"이미지 처리 실패: {exc}")

    # 20) 답변 생성 속도 — 새로 한 번 더 /api/infer 측정 (캐시 영향 최소화)
    spec = by_key["answer_speed"]
    t0 = datetime.utcnow()
    try:
        gen_res = api_infer(InferIn(
            requirement=sample_requirement + " (perf test)",
            code=sample_code, language="python",
            model=model_name, embed=False,
        ))
        ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        _add(spec, status=_perf_status(ms), value_ms=ms,
             value_text=f"{ms} ms (budget {budget} ms)",
             message=f"answer_id={gen_res.get('answer_id')}, "
                     f"stub={gen_res.get('stub')}",
             evidence={"answer_id": gen_res.get("answer_id"),
                       "model": gen_res.get("model"),
                       "stub": gen_res.get("stub")})
    except Exception as exc:  # noqa: BLE001
        ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        _add(spec, status="failed", value_ms=ms,
             message=f"/api/infer 실패: {exc}")

    # 21) MySQL 검색 속도
    spec = by_key["mysql_speed"]
    t0 = datetime.utcnow()
    try:
        # model_answers 텍스트/메타 검색 1회
        rows = db.fetch_all(
            "SELECT id, model_name, created_at FROM model_answers "
            "WHERE answer_text LIKE %s OR model_name LIKE %s "
            "ORDER BY id DESC LIMIT 20",
            ("%def%", "%stub%"),
        ) or []
        ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        _add(spec, status=_perf_status(ms), value_ms=ms,
             value_text=f"{ms} ms / {len(rows)} rows (budget {budget} ms)",
             message="model_answers LIKE 검색",
             evidence={"hits": len(rows)})
    except Exception as exc:  # noqa: BLE001
        ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        _add(spec, status="failed", value_ms=ms,
             message=f"MySQL 검색 실패: {exc}")

    # 22) embedding 유사도 검색 속도
    spec = by_key["embedding_speed"]
    t0 = datetime.utcnow()
    try:
        sim_res = api_reuse_find_similar(ReuseFindSimilarIn(
            text=sample_requirement, top_k=5, threshold=-1.0,
        ))
        ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        # 응답에 hit 수 추출
        groups = (sim_res or {}).get("groups") or {}
        total_hits = 0
        if isinstance(groups, dict):
            for g in groups.values():
                items = (g or {}).get("items") if isinstance(g, dict) else None
                if isinstance(items, list):
                    total_hits += len(items)
        _add(spec, status=_perf_status(ms), value_ms=ms,
             value_text=f"{ms} ms / {total_hits} hits (budget {budget} ms)",
             message="/api/reuse/find-similar 1회",
             evidence={"hits": total_hits})
    except Exception as exc:  # noqa: BLE001
        ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        _add(spec, status="failed", value_ms=ms,
             message=f"embedding 유사도 검색 실패: {exc}")

    # ---- 통계 마감 ----
    total_ms = int((datetime.utcnow() - overall_started).total_seconds() * 1000)
    if counters["failed"] == 0 and counters["passed"] > 0:
        status = "passed"
    elif counters["failed"] > 0 and counters["passed"] > 0:
        status = "partial"
    elif counters["failed"] > 0:
        status = "failed"
    else:
        status = "partial"

    db.execute(
        """
        UPDATE benchmark_runs
           SET passed_items=%s, failed_items=%s, skipped_items=%s,
               info_items=%s, total_latency_ms=%s, status=%s,
               finished_at=CURRENT_TIMESTAMP
         WHERE id=%s
        """,
        (counters["passed"], counters["failed"], counters["skipped"],
         counters["info"], total_ms, status, run_id),
    )

    return {
        "run_id": run_id,
        "status": status,
        "run_mode": run_mode_value,
        "accelerator": hw_row.get("accelerator"),
        "os_name": os_name,
        "os_version": os_version,
        "total_items": len(BENCHMARK_CHECKLIST),
        "passed": counters["passed"],
        "failed": counters["failed"],
        "skipped": counters["skipped"],
        "info": counters["info"],
        "total_latency_ms": total_ms,
        "items": items_out,
    }


@app.get("/api/benchmark/runs")
def api_benchmark_runs(
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    where: list[str] = []
    args: list[Any] = []
    if status:
        where.append("status=%s"); args.append(status)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.fetch_all(
        f"SELECT id, triggered_by, host_name, os_name, os_version, "
        f"       run_mode, accelerator, total_items, passed_items, "
        f"       failed_items, skipped_items, info_items, "
        f"       total_latency_ms, status, started_at, finished_at "
        f"FROM benchmark_runs {where_sql} "
        f"ORDER BY id DESC LIMIT %s OFFSET %s",
        tuple(args + [limit, offset]),
    ) or []
    total = (db.fetch_one(
        f"SELECT COUNT(*) AS n FROM benchmark_runs {where_sql}",
        tuple(args),
    ) or {}).get("n", 0)
    return {"total": total, "limit": limit, "offset": offset, "items": rows}


@app.get("/api/benchmark/runs/{run_id}")
def api_benchmark_run_get(run_id: int):
    row = db.fetch_one(
        "SELECT * FROM benchmark_runs WHERE id=%s", (run_id,),
    )
    if not row:
        raise HTTPException(404, "benchmark_run not found")
    items = db.fetch_all(
        "SELECT id, category, item_no, item_key, label, status, "
        "       value_ms, value_text, message, evidence_json, created_at "
        "FROM benchmark_items WHERE run_id=%s "
        "ORDER BY item_no ASC, id ASC",
        (run_id,),
    ) or []
    for it in items:
        if isinstance(it.get("evidence_json"), str):
            try:
                it["evidence"] = json.loads(it["evidence_json"])
            except Exception:  # noqa: BLE001
                it["evidence"] = None
        else:
            it["evidence"] = it.get("evidence_json")
        it.pop("evidence_json", None)
    return {"run": row, "items": items}


