"""
api/schemas.py
──────────────
Response/request models for the FastAPI service layer (Phase 2).

These mirror database/schema.py field-for-field rather than inventing a
parallel API shape — the repositories already return sqlite3.Row-derived
dicts with these exact keys, so the models here are a typed, documented
contract over data that already exists, not a new data model.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class JobOut(BaseModel):
    id: int
    file_path: str
    file_hash: str
    status: str
    total_records: int
    processed_count: int
    sent_count: int
    escalated_count: int
    failed_count: int
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


class UploadResponse(BaseModel):
    job_id: int
    status: str  # "started" | "duplicate_completed" | "in_progress"


class AuditLogOut(BaseModel):
    id: int
    job_id: int
    invoice_no: str
    client: str
    contact_email_masked: Optional[str] = None
    stage_key: Optional[str] = None
    tone_used: Optional[str] = None
    days_overdue: Optional[int] = None
    validation_status: Optional[str] = None
    send_status: Optional[str] = None
    retry_count: int = 0
    error_message: Optional[str] = None
    created_at: str


class FailedInvoiceOut(BaseModel):
    id: int
    job_id: int
    invoice_no: str
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int
    max_retries: int
    next_retry_at: Optional[str] = None
    status: str
    created_at: str
    updated_at: str


class RetryResult(BaseModel):
    failed_id: int
    outcome: str  # "resolved" | "retried" | "invalid_state" | "error"
    detail: Optional[str] = None


class CustomerHistoryOut(BaseModel):
    is_known_client: bool
    reminders_sent: int
    escalations: int
    emails_rejected_in_validation: int
    last_tone_used: Optional[str] = None
    last_interaction_at: Optional[str] = None


class GenerateInvoiceRequest(BaseModel):
    invoice_number: str
    client_name: str
    amount: float
    due_date: str
    recipient_email: str


class HealthOut(BaseModel):
    status: str
    service: str
