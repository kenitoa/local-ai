from fastapi import APIRouter, HTTPException

from app.schemas.jobs import JobResponse
from app.services.job_store import JobStore

router = APIRouter()


@router.get("/jobs")
def list_training_jobs() -> dict[str, list[dict[str, str]]]:
    return {"jobs": []}


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    job = JobStore().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**job)
