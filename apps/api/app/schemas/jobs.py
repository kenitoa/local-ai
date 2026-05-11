from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    id: str
    kind: str
    status: str
    result: dict[str, object] = Field(default_factory=dict)
