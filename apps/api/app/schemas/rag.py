from pydantic import BaseModel, Field


class RagIngestRequest(BaseModel):
    project_id: str
    paths: list[str] = Field(default_factory=list)
    collection: str = "project_code_chunks"


class RagIngestResponse(BaseModel):
    project_id: str
    collection: str
    indexed_count: int
    document_ids: list[str]


class RagSearchRequest(BaseModel):
    query: str
    project_id: str | None = None
    collection: str = "project_code_chunks"
    limit: int = 5
