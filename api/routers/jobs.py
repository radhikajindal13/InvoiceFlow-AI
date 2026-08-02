from fastapi import APIRouter, HTTPException, Query

from api.schemas import JobOut
from database.jobs_repository import JobsRepository

router = APIRouter(prefix="/jobs", tags=["jobs"])
_jobs_repo = JobsRepository()


@router.get("", response_model=list[JobOut])
def list_jobs(limit: int = Query(default=50, le=500)) -> list[JobOut]:
    return [JobOut(**row) for row in _jobs_repo.list_jobs(limit=limit)]


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int) -> JobOut:
    row = _jobs_repo.get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return JobOut(**row)
