"""
agents/coordinator.py
──────────────────────
Wires the risk_agent and verifier_agent into the existing per-invoice
AgentState / worker StateGraph as two additional nodes, and records the
outcome into long-term customer memory. This is the "coordinator"
referenced in the brief — for a single-invoice pipeline that's an honest
description of what's needed: a thin adapter deciding routing based on
agent output, not a tenth graph layer for its own sake.

New nodes (added to graphs/worker_graph.py, inserted *after* the existing,
unchanged validate_draft_email step):

    validate_draft_email (existing, approved)
        -> assess_risk_node          (NEW)
        -> verify_email_ai_node      (NEW)
        -> route_after_verification  (NEW conditional edge)
              approve      -> send_email
              needs_human  -> escalation
              reject       -> generate_email_draft (retry, same loop
                               pattern as the existing validator) or
                               escalation once retries are exhausted
"""

from __future__ import annotations

from typing import Literal

from agents.risk_agent import assess_risk
from agents.verifier_agent import verify_email
from core.models import AgentState
from database.memory_repository import CustomerMemoryRepository
from mcp.client import default_client
from memory.index import MemoryIndex
from memory.retrieval import MemoryRetrieval

_memory_repo = CustomerMemoryRepository()
_memory_index = MemoryIndex()
_memory_retrieval = MemoryRetrieval()


def assess_risk_node(state: AgentState) -> AgentState:
    invoice = state["invoice"]
    assessment = assess_risk(
        invoice_no=invoice["invoice_no"],
        client_name=invoice["client"],
        amount=invoice["amount"],
        days_overdue=state["days_overdue"],
    )
    return {
        **state,
        "risk_score": assessment.score,
        "risk_band": assessment.band,
        "risk_reasoning": assessment.reasoning,
    }


def verify_email_ai_node(state: AgentState) -> AgentState:
    invoice = state["invoice"]
    email_draft = state["email_draft"]
    body_text = " ".join([email_draft.greeting, email_draft.body, email_draft.closing])

    result = verify_email(
        body_text=body_text,
        invoice_no=invoice["invoice_no"],
        client_name=invoice["client"],
        days_overdue=state["days_overdue"],
        payment_link=state["payment_link"],
        amount_display=str(invoice["amount"]),
    )

    # A critical/high risk score independently escalates to human review
    # even if the verifier itself approved the email on facts alone.
    verdict = result.verdict
    if verdict == "approve" and state.get("risk_band") in ("high", "critical"):
        verdict = "needs_human"

    return {
        **state,
        "verification_verdict": verdict,
        "verification_confidence": result.confidence,
        "verification_reasoning": result.reasoning,
    }


def route_after_verification(
    state: AgentState,
) -> Literal["send_email_mcp", "escalation", "generate_email_draft"]:
    verdict = state.get("verification_verdict")

    if verdict == "approve":
        return "send_email_mcp"

    if verdict == "needs_human":
        return "escalation"

    # verdict == "reject": reuse the exact same retry/escalate pattern
    # as the existing deterministic validator.
    retry_count = state.get("retry_count", 0) + 1
    if retry_count >= state.get("max_retries", 3):
        return "escalation"
    return "generate_email_draft"


def record_outcome_node(state: AgentState) -> AgentState:
    """Persist this invoice's outcome into long-term customer memory so
    future risk/verifier agent calls for this client have real history to
    reason over. Runs as part of auditLog, after send/escalation."""
    invoice = state["invoice"]
    email_draft = state.get("email_draft")

    _memory_repo.record_interaction(
        invoice["client"],
        reminder_sent=state.get("send_status") == "sent",
        escalated=bool(state.get("escalation_required")),
        validation_rejected=state.get("validation_status") == "rejected",
        tone_used=email_draft.tone if email_draft else None,
    )
    return state


# ─────────────────────────────────────────────────────────────────────────
# Phase 3: MCP integration
#
# These two nodes are what "the coordinator invokes MCP tools instead of
# calling services directly" (brief requirement) means concretely in this
# graph. They replace graphs/worker_graph.py's send_email_node and the
# escalation -> auditLog edge respectively. send_email_node itself is left
# completely intact and still importable/testable — it's just no longer
# wired into the compiled graph, superseded by send_email_via_mcp_node.
# ─────────────────────────────────────────────────────────────────────────

def send_email_via_mcp_node(state: AgentState) -> AgentState:
    """
    Send the approved, verified email draft through the MCP Outlook
    connector (mcp/connectors/outlook.py) instead of importing and
    calling core.email_service.send_email directly. The connector itself
    still delegates to that same real send_email function underneath —
    what changes is that the coordinator now goes through
    default_client.call_tool(...), the same interface it would use for
    any other MCP tool, so swapping providers or adding logging/retries
    later happens at the connector layer without touching this node.
    """
    email_draft = state.get("email_draft")

    if not email_draft:
        return {
            **state,
            "send_status": "failed",
            "send_error": "No email draft available to send.",
        }

    body = "\n\n".join(filter(None, [
        getattr(email_draft, "greeting", "").strip(),
        getattr(email_draft, "body", "").strip(),
        getattr(email_draft, "closing", "").strip(),
    ]))

    call_result = default_client.call_tool(
        "outlook.send_email",
        {
            "to": str(email_draft.recipient),
            "subject": email_draft.subject,
            "body": body,
            "invoice_no": state["invoice"]["invoice_no"],
            "tone": email_draft.tone,
        },
    )

    if call_result.success and call_result.result.get("success"):
        provider = call_result.result.get("provider", "outlook")
        dry_run_tag = "·DRY-RUN" if call_result.result.get("dry_run") else ""
        print(f"\n[MCP·{provider.upper()}{dry_run_tag}] Follow-up email sent -> {email_draft.recipient}")
        print(f"  Subject : {email_draft.subject}")
        print(f"  Detail  : {call_result.result.get('message')}")
        return {**state, "send_status": "sent", "send_error": ""}

    error_detail = call_result.error or call_result.result
    print(f"\n[MCP·OUTLOOK ERROR] {error_detail}")
    return {
        **state,
        "send_status": "failed",
        "send_error": f"MCP outlook.send_email failed: {error_detail}",
    }


def notify_escalation_via_mcp_node(state: AgentState) -> AgentState:
    """
    Runs after escalation_node (unchanged). Files a Jira ticket and posts
    a Slack notification via MCP tools — the concrete realization of the
    original brief's "Escalation Agent -> Notification Agent" handoff,
    scoped to what this system can act on for real: no email to the
    client (escalation_node already enforces that), but a real internal
    paper trail via Jira + Slack.
    """
    invoice = state["invoice"]
    reason = state.get("send_error", "Escalated for manual review")

    jira_result = default_client.call_tool(
        "jira.create_jira_ticket",
        {
            "summary": f"Overdue invoice follow-up: {invoice['invoice_no']} ({invoice['client']})",
            "description": (
                f"Invoice {invoice['invoice_no']} for {invoice['client']} "
                f"(amount: {invoice['amount']}) was escalated by the AI "
                f"follow-up agent.\nReason: {reason}"
            ),
            "priority": "High" if state.get("days_overdue", 0) > 30 else "Medium",
        },
    )

    ticket_key = jira_result.result.get("ticket_key") if jira_result.success else None
    slack_message = (
        f":warning: Invoice *{invoice['invoice_no']}* ({invoice['client']}) escalated. "
        f"Reason: {reason}."
        + (f" Jira: {ticket_key}" if ticket_key else "")
    )

    slack_result = default_client.call_tool(
        "slack.send_slack_message",
        {"channel": "#finance-alerts", "message": slack_message},
    )

    return {
        **state,
        "escalation_ticket_key": ticket_key,
        "escalation_notified": bool(jira_result.success and slack_result.success),
    }


# ─────────────────────────────────────────────────────────────────────────
# Phase 4: semantic memory / RAG
#
# retrieve_memory_node realizes the brief's RAG workflow:
#     Search vector database -> Retrieve relevant history -> Inject context
# (the fourth step, "Generate response", is generate_email_draft itself —
# unchanged except that it now reads state["retrieved_context"], see
# core/prompts.py's new {relevant_history} placeholder).
#
# index_semantic_memory_node is the write side: after an outcome is known
# (sent or escalated), the interaction is embedded and stored so it
# becomes retrievable context for this client's *next* invoice.
# ─────────────────────────────────────────────────────────────────────────

def retrieve_memory_node(state: AgentState) -> AgentState:
    invoice = state["invoice"]
    query_text = (
        f"Invoice {invoice['invoice_no']} for {invoice['client']}, "
        f"amount {invoice['amount']}, {state['days_overdue']} days overdue, "
        f"stage {state.get('stage_key', '')}"
    )
    context = _memory_retrieval.get_context_for_email(
        client_name=invoice["client"],
        query_text=query_text,
    )
    return {**state, "retrieved_context": context}


def index_semantic_memory_node(state: AgentState) -> AgentState:
    invoice = state["invoice"]
    client_name = invoice["client"]
    email_draft = state.get("email_draft")

    if email_draft and state.get("send_status") == "sent":
        body = " ".join(filter(None, [email_draft.greeting, email_draft.body, email_draft.closing]))
        _memory_index.add_email(
            client_name=client_name,
            invoice_no=invoice["invoice_no"],
            text=f"[{email_draft.tone}] {body}",
            metadata={"days_overdue": state.get("days_overdue"), "stage_key": state.get("stage_key")},
        )

    if state.get("risk_score") is not None:
        _memory_index.add_risk_assessment(
            client_name=client_name,
            invoice_no=invoice["invoice_no"],
            text=(
                f"Risk band {state.get('risk_band')} (score {state.get('risk_score')}): "
                f"{state.get('risk_reasoning', '')}"
            ),
            metadata={"band": state.get("risk_band"), "score": state.get("risk_score")},
        )

    if state.get("escalation_ticket_key"):
        _memory_index.add_approval(
            client_name=client_name,
            invoice_no=invoice["invoice_no"],
            text=(
                f"Invoice {invoice['invoice_no']} escalated, Jira ticket "
                f"{state['escalation_ticket_key']}. Reason: {state.get('send_error', '')}"
            ),
            metadata={"ticket_key": state["escalation_ticket_key"]},
        )

    _memory_index.add_invoice_history(
        client_name=client_name,
        invoice_no=invoice["invoice_no"],
        text=(
            f"Invoice {invoice['invoice_no']}, amount {invoice['amount']}, "
            f"{state.get('days_overdue')} days overdue, outcome: "
            f"{state.get('send_status', 'not_sent')}"
        ),
        metadata={"days_overdue": state.get("days_overdue")},
    )

    return state
