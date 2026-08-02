"""
agents/tools.py
───────────────
Real tools the LLM can call, each with a description + argument schema
(enforced by @tool + Pydantic, exactly like the existing EmailDraft schema
enforcement in core/models.py). Every tool is backed by the *existing*
repository layer — no new services, no mocked data stores.

Tools:
    lookup_customer_history  — reads database/memory_repository.py
    fetch_invoice_history    — reads database/audit_repository.py (new
                                get_by_invoice_no method)
    calculate_risk_score      — deterministic scoring, no LLM involved
    verify_email_facts        — deterministic fact-check for the
                                 hallucination-verifier agent

`calculate_risk_score` and `verify_email_facts` are intentionally
deterministic Python, not LLM calls, even though they're exposed as tools
an LLM can invoke: risk numbers and fact checks should be computed, not
generated, so an agent orchestrates *when* to call them but never
hallucinates the number or the check result itself.
"""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from database.audit_repository import AuditRepository
from database.memory_repository import CustomerMemoryRepository

_audit_repo = AuditRepository()
_memory_repo = CustomerMemoryRepository()


# ─── lookup_customer_history ────────────────────────────────────────────────

class CustomerHistoryArgs(BaseModel):
    client_name: str = Field(description="Exact client/company name as it appears on the invoice")


@tool("lookup_customer_history", args_schema=CustomerHistoryArgs)
def lookup_customer_history(client_name: str) -> dict:
    """Look up a client's persistent behavioral history: how many reminders
    they've received before, how many times they've been escalated, how many
    generated emails were rejected in validation, and the tone last used with
    them. Returns is_known_client=False with zeroed counters for a client
    seen for the first time."""
    summary = _memory_repo.get_summary(client_name)
    if not summary:
        return {
            "is_known_client": False,
            "reminders_sent": 0,
            "escalations": 0,
            "emails_rejected_in_validation": 0,
            "last_tone_used": None,
            "last_interaction_at": None,
        }
    return {
        "is_known_client": True,
        "reminders_sent": summary["reminders_sent"],
        "escalations": summary["escalations"],
        "emails_rejected_in_validation": summary["emails_rejected_in_validation"],
        "last_tone_used": summary["last_tone_used"],
        "last_interaction_at": summary["last_interaction_at"],
    }


# ─── fetch_invoice_history ───────────────────────────────────────────────────

class InvoiceHistoryArgs(BaseModel):
    invoice_no: str = Field(description="Invoice number to look up, e.g. INV-2026-101")


@tool("fetch_invoice_history", args_schema=InvoiceHistoryArgs)
def fetch_invoice_history(invoice_no: str) -> dict:
    """Fetch this invoice's own prior audit trail (previous follow-up
    attempts, prior validation outcomes, prior send/escalation status)
    across every job it has appeared in. Returns attempt_count=0 if this
    is the first time this invoice has been processed."""
    rows = _audit_repo.get_by_invoice_no(invoice_no)
    return {
        "attempt_count": len(rows),
        "attempts": [
            {
                "stage_key": r.get("stage_key"),
                "validation_status": r.get("validation_status"),
                "send_status": r.get("send_status"),
                "retry_count": r.get("retry_count"),
                "created_at": r.get("created_at"),
            }
            for r in rows
        ],
    }


# ─── calculate_risk_score ────────────────────────────────────────────────────

class RiskScoreArgs(BaseModel):
    days_overdue: int = Field(description="Number of days the invoice is overdue")
    amount: float = Field(description="Invoice amount")
    prior_escalations: int = Field(default=0, description="Times this client has been escalated before")
    prior_rejections: int = Field(default=0, description="Times this client's emails failed validation before")
    invoice_attempt_count: int = Field(default=0, description="Times this specific invoice has already been processed")


@tool("calculate_risk_score", args_schema=RiskScoreArgs)
def calculate_risk_score(
    days_overdue: int,
    amount: float,
    prior_escalations: int = 0,
    prior_rejections: int = 0,
    invoice_attempt_count: int = 0,
) -> dict:
    """Deterministically compute a 0-100 non-payment risk score from
    overdue duration, invoice size, and this client/invoice's own history.
    This is a calculation, not a model guess — call it with real numbers
    gathered from lookup_customer_history / fetch_invoice_history rather
    than estimating the score yourself."""
    score = 0.0
    reasons: list[str] = []

    # Overdue duration — the single strongest signal
    duration_component = min(days_overdue, 60) / 60 * 45
    score += duration_component
    if days_overdue > 30:
        reasons.append(f"{days_overdue} days overdue (past escalation threshold)")
    elif days_overdue > 14:
        reasons.append(f"{days_overdue} days overdue (moderate delay)")

    # Invoice size — larger invoices carry more exposure
    size_component = min(amount, 500_000) / 500_000 * 20
    score += size_component
    if amount >= 100_000:
        reasons.append(f"large invoice amount ({amount:,.0f})")

    # This client's track record
    history_component = min(prior_escalations * 15 + prior_rejections * 5, 25)
    score += history_component
    if prior_escalations:
        reasons.append(f"{prior_escalations} prior escalation(s) for this client")
    if prior_rejections:
        reasons.append(f"{prior_rejections} prior validation rejection(s) for this client")

    # This invoice going in circles
    attempt_component = min(invoice_attempt_count * 5, 10)
    score += attempt_component
    if invoice_attempt_count >= 2:
        reasons.append(f"this invoice has already been processed {invoice_attempt_count} time(s)")

    score = round(min(score, 100), 1)

    if score >= 75:
        band = "critical"
    elif score >= 50:
        band = "high"
    elif score >= 25:
        band = "medium"
    else:
        band = "low"

    if not reasons:
        reasons.append("no material risk factors found")

    return {"score": score, "band": band, "reasons": reasons}


# ─── verify_email_facts ──────────────────────────────────────────────────────

class VerifyEmailFactsArgs(BaseModel):
    body_text: str = Field(description="Full assembled email text (greeting + body + closing)")
    invoice_no: str = Field(description="Ground-truth invoice number")
    client_name: str = Field(description="Ground-truth client name")
    days_overdue: int = Field(description="Ground-truth days overdue")
    payment_link: str = Field(description="Ground-truth payment link")
    amount_display: str = Field(description="Ground-truth formatted amount, e.g. 'INR 45,250.75'")


@tool("verify_email_facts", args_schema=VerifyEmailFactsArgs)
def verify_email_facts(
    body_text: str,
    invoice_no: str,
    client_name: str,
    days_overdue: int,
    payment_link: str,
    amount_display: str,
) -> dict:
    """Deterministically check whether a generated email actually contains
    the required ground-truth facts (invoice number, client name, days
    overdue, payment link, amount) rather than trusting the model's own
    self-report. Returns which required facts are missing, if any."""
    missing: list[str] = []
    checks = {
        "invoice_no": invoice_no,
        "client_name": client_name,
        "days_overdue": str(days_overdue),
        "payment_link": payment_link,
    }
    for label, value in checks.items():
        if value and str(value) not in body_text:
            missing.append(label)

    # Amount is checked loosely (formatting varies) — require the raw digits
    digits_only = "".join(ch for ch in amount_display if ch.isdigit())
    if digits_only and digits_only[:6] not in "".join(ch for ch in body_text if ch.isdigit()):
        missing.append("amount")

    return {
        "all_facts_present": len(missing) == 0,
        "missing_facts": missing,
    }


ALL_TOOLS = [
    lookup_customer_history,
    fetch_invoice_history,
    calculate_risk_score,
    verify_email_facts,
]
