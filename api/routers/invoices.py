"""
api/routers/invoices.py
────────────────────────
POST /invoices/generate — run a single invoice through the exact same
worker graph (graphs/worker_graph.py::agent) the CSV pipeline uses,
without requiring a CSV upload. Reuses the identical normalization logic
from graphs/master_graph.py::normalize_records so an ad-hoc API call and a
CSV row produce identical AgentState — no parallel code path.
"""

import uuid

from fastapi import APIRouter

from api.schemas import GenerateInvoiceRequest
from core.utils import get_overdue_days, get_stage_meta
from graphs.worker_graph import agent as worker

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.post("/generate")
def generate_invoice_email(request: GenerateInvoiceRequest) -> dict:
    days_overdue = get_overdue_days(request.due_date)
    if days_overdue is None:
        return {"error": f"Could not parse due_date: {request.due_date}"}

    stage_details = get_stage_meta(days_overdue)

    invoice_state = {
        "invoice": {
            "invoice_no": request.invoice_number,
            "client": request.client_name,
            "amount": request.amount,
            "due_date": request.due_date,
            "contact_email": request.recipient_email,
            "followup_count": 1,
        },
        "days_overdue": days_overdue,
        "stage_key": stage_details["stage_key"],
        "stage_meta": stage_details["stage_meta"],
        "escalation_required": stage_details["stage_meta"]["escalation_required"],
        "retry_count": 0,
        "max_retries": 3,
    }

    config = {
        "run_name": f"API Generate {request.invoice_number}",
        "tags": ["api", "worker"],
        "configurable": {"thread_id": f"api-invoice-{request.invoice_number}-{uuid.uuid4().hex[:8]}"},
    }

    result = worker.invoke(invoice_state, config=config)
    return result.get("audit_log", {"error": "No audit log produced", "raw_state_keys": list(result.keys())})
