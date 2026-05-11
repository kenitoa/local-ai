from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    file_count: int = 0


class ProjectFileUploadRequest(BaseModel):
    path: str
    content: str
    language: str = Field(default="text")


class ProjectFileResponse(BaseModel):
    project_id: str
    path: str
    language: str
    bytes: int
