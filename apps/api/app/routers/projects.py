from fastapi import APIRouter, HTTPException

from app.schemas.projects import (
    ProjectCreateRequest,
    ProjectFileResponse,
    ProjectFileUploadRequest,
    ProjectResponse,
)
from app.services.project_store import ProjectStore

router = APIRouter()


@router.post("", response_model=ProjectResponse)
def create_project(payload: ProjectCreateRequest) -> ProjectResponse:
    return ProjectResponse(**ProjectStore().create_project(payload.name, payload.description))


@router.get("", response_model=list[ProjectResponse])
def list_projects() -> list[ProjectResponse]:
    return [ProjectResponse(**project) for project in ProjectStore().list_projects()]


@router.post("/{project_id}/files", response_model=ProjectFileResponse)
def upload_project_file(
    project_id: str,
    payload: ProjectFileUploadRequest,
) -> ProjectFileResponse:
    try:
        record = ProjectStore().save_file(
            project_id=project_id,
            path=payload.path,
            content=payload.content,
            language=payload.language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProjectFileResponse(**record)
