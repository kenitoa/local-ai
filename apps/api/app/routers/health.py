from fastapi import APIRouter

from app.config import settings
from app.services.rag_service import RagService
from app.services.secrets import has_secret

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
    }


@router.get("/ready")
def readiness_check() -> dict[str, object]:
    rag = RagService()
    rag_ready = rag.is_ready()
    return {
        "status": "ready" if rag_ready else "degraded",
        "environment": settings.app_env,
        "ai_device": settings.ai_device,
        "llm_backend": settings.llm_backend,
        "llm_model": settings.llm_model,
        "model_backend": settings.model_backend,
        "base_model_path": settings.base_model_path,
        "lora": {
            "enabled": settings.lora_enabled,
            "adapter_name": settings.lora_adapter_name,
            "adapter_path": settings.lora_adapter_path,
        },
        "secrets": {
            "hf_token": has_secret("hf_token"),
        },
        "dependencies": {
            "storage": True,
            "rag_index": rag_ready,
            "rag_backend": rag.backend_name(),
        },
    }
