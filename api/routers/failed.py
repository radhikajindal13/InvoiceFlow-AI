from fastapi import APIRouter, HTTPException, Query

from api.schemas import FailedInvoiceOut, RetryResult
from database.failed_repository import FailedInvoicesRepository
from scheduler.retry_scheduler import retry_one

router = APIRouter(prefix="/failed", tags=["failed"])
_failed_repo = FailedInvoicesRepository()


@router.get("", response_model=list[FailedInvoiceOut])
def list_failed(limit: int = Query(default=100, le=1000)) -> list[FailedInvoiceOut]:
    return [FailedInvoiceOut(**row) for row in _failed_repo.list_all(limit=limit)]


@router.post("/{failed_id}/retry", response_model=RetryResult)
def retry_failed_invoice(failed_id: int) -> RetryResult:
    """
    Manually retry one failed invoice on demand, instead of waiting for the
    next APScheduler interval. Reuses scheduler/retry_scheduler.py::retry_one
    — the exact same code path the scheduler itself calls — so a manual
    retry and a scheduled retry can never behave differently.
    """
    row = _failed_repo.get_by_id(failed_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Failed invoice {failed_id} not found")
    if row["status"] not in ("pending",):
        raise HTTPException(
            status_code=409,
            detail=f"Failed invoice {failed_id} has status '{row['status']}', not retryable",
        )

    result = retry_one(row)
    return RetryResult(**result)
