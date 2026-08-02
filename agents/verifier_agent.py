"""
agents/verifier_agent.py
────────────────────────
Hallucination-Detector / Verifier Agent (brief Step 11).

    Generated Email → Verifier → approve | reject | needs_human

This sits *after* the existing deterministic validate_draft_email node in
graphs/worker_graph.py (which is left completely unchanged — recipient/
tone/subject-template checks still run exactly as before). This agent adds
a second, independent pass focused specifically on fact hallucination:
does the email actually contain the real invoice number, client name,
days overdue, payment link, and amount — checked with the same
verify_email_facts tool a human reviewer's checklist would use, not by
asking the model to grade its own homework.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agents.base import run_tool_agent
from agents.tools import ALL_TOOLS, verify_email_facts
from core.models import model

SYSTEM_PROMPT = """You are a fact-verification agent reviewing an
AI-generated invoice follow-up email before it is sent. You MUST call
verify_email_facts with the actual email text and the ground-truth values
provided — do not judge factual correctness from reading the email alone,
since your own reading can miss subtle date/amount/name substitutions.
You may also call fetch_invoice_history to check whether this invoice has
a troubled history (repeated rejections/escalations) that warrants human
review even if the facts check out. Conclude with exactly one verdict:
'approve' (facts check out, safe to send), 'reject' (facts are wrong, the
email should be regenerated), or 'needs_human' (facts check out but the
situation - e.g. a long history of disputes - warrants a human look
before sending)."""


class VerificationResult(BaseModel):
    verdict: Literal["approve", "reject", "needs_human"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    missing_facts: list[str] = Field(default_factory=list)


def verify_email(
    *,
    body_text: str,
    invoice_no: str,
    client_name: str,
    days_overdue: int,
    payment_link: str,
    amount_display: str,
) -> VerificationResult:
    fact_check = verify_email_facts.invoke(
        {
            "body_text": body_text,
            "invoice_no": invoice_no,
            "client_name": client_name,
            "days_overdue": days_overdue,
            "payment_link": payment_link,
            "amount_display": amount_display,
        }
    )

    if not fact_check["all_facts_present"]:
        # No need to spend a model call on this: the deterministic check
        # already found a hallucinated/missing fact, which is a hard reject.
        return VerificationResult(
            verdict="reject",
            confidence=1.0,
            reasoning=f"Missing required facts: {', '.join(fact_check['missing_facts'])}",
            missing_facts=fact_check["missing_facts"],
        )

    user_message = (
        f"Email body:\n{body_text}\n\n"
        f"Ground truth — invoice: {invoice_no}, client: {client_name}, "
        f"days_overdue: {days_overdue}, payment_link: {payment_link}, "
        f"amount: {amount_display}.\n\n"
        "verify_email_facts already confirmed all required facts are "
        "present. Now check invoice history and give your final verdict."
    )
    result = run_tool_agent(model, ALL_TOOLS, SYSTEM_PROMPT, user_message)

    structured = model.with_structured_output(VerificationResult).invoke(
        f"Based on this analysis, produce the final structured verdict:\n{result.text}"
    )
    return structured
