from typing import Optional

from fastapi import APIRouter, Query

from api.schemas import AuditLogOut
from database.audit_repository import AuditRepository

router = APIRouter(prefix="/audit", tags=["audit"])
_audit_repo = AuditRepository()


@router.get("", response_model=list[AuditLogOut])
def get_audit_logs(
    job_id: Optional[int] = Query(default=None, description="Filter to one job"),
    limit: int = Query(default=100, le=1000),
) -> list[AuditLogOut]:
    if job_id is not None:
        rows = _audit_repo.get_by_job(job_id)[:limit]
    else:
        rows = _audit_repo.list_recent(limit=limit)
    return [AuditLogOut(**row) for row in rows]
