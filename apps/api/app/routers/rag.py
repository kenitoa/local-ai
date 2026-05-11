from fastapi import APIRouter

from adapters.api_optional.routes import call_adapter, get_adapter
from app.schemas.rag import RagIngestRequest, RagIngestResponse, RagSearchRequest

router = APIRouter()


@router.post("/ingest", response_model=RagIngestResponse)
def ingest(payload: RagIngestRequest) -> RagIngestResponse:
    return call_adapter(lambda: get_adapter().ingest_rag(payload))


@router.post("/search")
def search(payload: RagSearchRequest) -> dict[str, object]:
    return call_adapter(lambda: get_adapter().search_rag(payload))
