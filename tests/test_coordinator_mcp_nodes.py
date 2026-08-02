"""
tests/test_coordinator_mcp_nodes.py
─────────────────────────────────────
Directly exercises agents/coordinator.py::send_email_via_mcp_node and
notify_escalation_via_mcp_node against synthetic AgentState dicts — no
LLM required (both nodes are pure MCP tool calls), no full graph needed.
"""
from core.models import EmailDraft


def _invoice(**overrides):
    base = {
        "invoice_no": "INV-COORD-001",
        "client": "Coordinator Test Co",
        "amount": 15000.0,
        "due_date": "1 Jan 2026",
        "contact_email": "billing@coordtest.com",
        "followup_count": 1,
    }
    base.update(overrides)
    return base


def test_send_email_via_mcp_node_success(monkeypatch, tmp_path):
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)
    from agents.coordinator import send_email_via_mcp_node

    draft = EmailDraft(
        recipient="billing@coordtest.com",
        subject="Payment Reminder",
        greeting="Hi team,",
        body="Your invoice is overdue.",
        closing="Regards, Finance",
        tone="Warm & Friendly",
    )
    state = {
        "invoice": _invoice(),
        "email_draft": draft,
    }

    result = send_email_via_mcp_node(state)
    assert result["send_status"] == "sent"
    assert result["send_error"] == ""


def test_send_email_via_mcp_node_no_draft():
    from agents.coordinator import send_email_via_mcp_node

    state = {"invoice": _invoice(), "email_draft": None}
    result = send_email_via_mcp_node(state)
    assert result["send_status"] == "failed"
    assert "No email draft" in result["send_error"]


def test_notify_escalation_via_mcp_node_creates_ticket_and_notifies(monkeypatch, tmp_path):
    import mcp.dry_run_log as dry_run_log_module
    import mcp.connectors.jira as jira_module

    log_path = tmp_path / "mcp_dry_run.jsonl"
    monkeypatch.setattr(dry_run_log_module, "MCP_DRY_RUN_LOG_PATH", log_path)
    monkeypatch.setattr(jira_module, "MCP_DRY_RUN_LOG_PATH", log_path)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

    from agents.coordinator import notify_escalation_via_mcp_node

    state = {
        "invoice": _invoice(),
        "days_overdue": 35,
        "send_error": "35 days overdue — flagged for legal/finance review",
    }

    result = notify_escalation_via_mcp_node(state)

    assert result["escalation_notified"] is True
    assert result["escalation_ticket_key"].startswith("FIN-")
    assert log_path.exists()

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert any('"tool": "create_jira_ticket"' in line for line in lines)
    assert any('"tool": "send_slack_message"' in line for line in lines)
