"""
api/routers/upload.py
──────────────────────
Wraps the existing core/upload_handler.py::handle_csv_upload — the same
dedup-by-SHA-256 + background-thread dispatch used by the Streamlit UI —
behind POST /upload, so the CSV pipeline works for programmatic callers
without changing anything about how a job actually runs.
"""

import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from api.schemas import UploadResponse
from core.upload_handler import handle_csv_upload

router = APIRouter(prefix="/upload", tags=["upload"])

_STATUS_MAP = {
    False: "started",
    True: "duplicate_completed",
    "in_progress": "in_progress",
}


@router.post("", response_model=UploadResponse)
async def upload_csv(file: UploadFile) -> UploadResponse:
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        job_id, dup_status = handle_csv_upload(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return UploadResponse(job_id=job_id, status=_STATUS_MAP[dup_status])
