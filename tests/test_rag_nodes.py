"""
tests/test_rag_nodes.py
---------------------------
Directly exercises agents/coordinator.py::retrieve_memory_node and
index_semantic_memory_node against synthetic AgentState dicts -- no LLM,
no full graph invocation needed (both nodes are pure memory operations).
"""
from core.models import EmailDraft


def _invoice(**overrides):
    base = {
        "invoice_no": "INV-RAG-NODE-001",
        "client": "RAG Node Test Client",
        "amount": 22000.0,
        "due_date": "1 Jan 2026",
        "contact_email": "billing@ragnode.com",
        "followup_count": 1,
    }
    base.update(overrides)
    return base


def test_retrieve_memory_node_no_prior_history():
    from agents.coordinator import retrieve_memory_node

    state = {"invoice": _invoice(client="RAG Node Unseen Client"), "days_overdue": 10, "stage_key": "1st Follow-Up"}
    result = retrieve_memory_node(state)
    assert result["retrieved_context"] == "No prior history available for this client."


def test_retrieve_memory_node_finds_prior_email():
    from agents.coordinator import retrieve_memory_node
    from memory.index import MemoryIndex

    MemoryIndex().add_email(
        client_name="RAG Node Known Client",
        invoice_no="INV-RAG-NODE-OLD",
        text="Sent a polite reminder about a previous overdue invoice payment.",
    )

    state = {
        "invoice": _invoice(client="RAG Node Known Client"),
        "days_overdue": 12,
        "stage_key": "2nd Follow-Up",
    }
    result = retrieve_memory_node(state)
    assert "reminder" in result["retrieved_context"].lower()


def test_index_semantic_memory_node_stores_sent_email():
    from agents.coordinator import index_semantic_memory_node
    from memory.retrieval import MemoryRetrieval

    draft = EmailDraft(
        recipient="billing@ragnode.com",
        subject="Payment Reminder",
        greeting="Hi team,",
        body="Your invoice INV-RAG-NODE-002 is overdue.",
        closing="Regards, Finance",
        tone="Polite but Firm",
    )
    state = {
        "invoice": _invoice(client="RAG Node Index Client", invoice_no="INV-RAG-NODE-002"),
        "email_draft": draft,
        "send_status": "sent",
        "days_overdue": 15,
        "stage_key": "2nd Follow-Up",
    }

    index_semantic_memory_node(state)

    ret = MemoryRetrieval()
    results = ret.search(query_text="invoice overdue reminder", client_name="RAG Node Index Client", limit=10)
    types_found = {r.record.memory_type.value for r in results}
    assert "email" in types_found
    assert "invoice_history" in types_found


def test_index_semantic_memory_node_stores_risk_and_approval():
    from agents.coordinator import index_semantic_memory_node
    from memory.retrieval import MemoryRetrieval

    state = {
        "invoice": _invoice(client="RAG Node Risk Client", invoice_no="INV-RAG-NODE-003"),
        "email_draft": None,
        "send_status": "not_sent",
        "days_overdue": 45,
        "stage_key": "Escalation",
        "risk_score": 88.0,
        "risk_band": "critical",
        "risk_reasoning": "Client has a history of repeated escalations.",
        "escalation_ticket_key": "FIN-99",
        "send_error": "45 days overdue",
    }

    index_semantic_memory_node(state)

    ret = MemoryRetrieval()
    results = ret.search(query_text="risk escalation ticket", client_name="RAG Node Risk Client", limit=10)
    types_found = {r.record.memory_type.value for r in results}
    assert "risk_assessment" in types_found
    assert "approval" in types_found
    # email_draft was None and send_status wasn't "sent" -> no email memory written
    assert "email" not in types_found


def test_index_semantic_memory_node_does_not_store_email_when_not_sent():
    from agents.coordinator import index_semantic_memory_node
    from memory.retrieval import MemoryRetrieval

    draft = EmailDraft(
        recipient="billing@ragnode.com",
        subject="Payment Reminder",
        greeting="Hi,",
        body="Body.",
        closing="Regards, Finance",
        tone="Warm & Friendly",
    )
    state = {
        "invoice": _invoice(client="RAG Node Failed Send Client", invoice_no="INV-RAG-NODE-004"),
        "email_draft": draft,
        "send_status": "failed",
        "days_overdue": 10,
        "stage_key": "1st Follow-Up",
    }

    index_semantic_memory_node(state)

    ret = MemoryRetrieval()
    results = ret.search(query_text="reminder", client_name="RAG Node Failed Send Client", limit=10)
    types_found = {r.record.memory_type.value for r in results}
    assert "email" not in types_found
    assert "invoice_history" in types_found  # invoice history is always recorded
