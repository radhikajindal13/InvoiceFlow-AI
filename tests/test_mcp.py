"""
tests/test_mcp.py
───────────────────
Deterministic, no-network unit tests for the mcp/ package. Every
connector here is either a real reuse of an already-dry-run-safe service
(outlook -> core.email_service, EMAIL_PROVIDER unset -> dry_run) or an
explicit mock (sap, crm, jira, slack, google_sheets all default to
dry-run/deterministic-mock behavior with no external credentials set) —
so this whole file runs with zero network access and zero LLM calls,
same as tests/test_tools.py.
"""
from pydantic import BaseModel, Field

from mcp.client import MCPClient, build_default_registry
from mcp.connector import BaseConnector
from mcp.registry import ConnectorRegistry


# ─── A minimal fake connector, used to test the generic interface itself
#     in isolation from any real connector's business logic ─────────────

class _PingArgs(BaseModel):
    value: int = Field(description="A number to echo back")


class _FakeConnector(BaseConnector):
    connector_name = "fake"

    def __init__(self):
        super().__init__()
        self.tool(name="ping", description="Echoes value back", args_schema=_PingArgs)(self._ping)
        self.tool(name="boom", description="Always raises", args_schema=_PingArgs)(self._boom)

    def _ping(self, value: int) -> dict:
        return {"echo": value}

    def _boom(self, value: int) -> dict:
        raise RuntimeError("simulated connector failure")


# ─── BaseConnector: schema, validation, logging, error handling ─────────

def test_connector_lists_registered_tools_with_json_schema():
    connector = _FakeConnector()
    specs = connector.list_tools()
    names = {s.name for s in specs}
    assert names == {"ping", "boom"}
    ping_spec = next(s for s in specs if s.name == "ping")
    assert ping_spec.qualified_name == "fake.ping"
    assert "value" in ping_spec.input_schema["properties"]


def test_connector_call_tool_success():
    connector = _FakeConnector()
    result = connector.call_tool("ping", {"value": 42})
    assert result.success is True
    assert result.result == {"echo": 42}
    assert result.error is None
    assert result.duration_ms >= 0


def test_connector_call_tool_validation_error_never_runs_handler():
    connector = _FakeConnector()
    result = connector.call_tool("ping", {"value": "not-an-int"})
    assert result.success is False
    assert "validation" in result.error.lower()


def test_connector_call_tool_missing_argument():
    connector = _FakeConnector()
    result = connector.call_tool("ping", {})
    assert result.success is False
    assert result.error is not None


def test_connector_call_tool_unknown_tool_name():
    connector = _FakeConnector()
    result = connector.call_tool("does_not_exist", {"value": 1})
    assert result.success is False
    assert "not found" in result.error.lower()


def test_connector_call_tool_catches_handler_exception():
    """A connector bug (or a real external API erroring) must come back as
    a normal failed ToolCallResult, never as a raised exception — this is
    what keeps one bad external call from taking down the graph."""
    connector = _FakeConnector()
    result = connector.call_tool("boom", {"value": 1})
    assert result.success is False
    assert "simulated connector failure" in result.error


# ─── ConnectorRegistry: registration, discovery, execution ──────────────

def test_registry_register_and_list_tools():
    registry = ConnectorRegistry()
    registry.register(_FakeConnector())
    tools = registry.list_tools()
    assert [t.qualified_name for t in tools] == ["fake.ping", "fake.boom"]


def test_registry_rejects_duplicate_connector_name():
    registry = ConnectorRegistry()
    registry.register(_FakeConnector())
    try:
        registry.register(_FakeConnector())
        assert False, "expected ValueError on duplicate registration"
    except ValueError:
        pass


def test_registry_call_tool_dispatches_by_qualified_name():
    registry = ConnectorRegistry()
    registry.register(_FakeConnector())
    result = registry.call_tool("fake.ping", {"value": 7})
    assert result.success is True
    assert result.result == {"echo": 7}


def test_registry_call_tool_unqualified_name_is_rejected():
    registry = ConnectorRegistry()
    registry.register(_FakeConnector())
    result = registry.call_tool("ping", {"value": 7})
    assert result.success is False
    assert "qualified" in result.error.lower()


def test_registry_call_tool_unknown_connector():
    registry = ConnectorRegistry()
    result = registry.call_tool("nope.ping", {"value": 1})
    assert result.success is False
    assert "no connector registered" in result.error.lower()


def test_registry_as_langchain_tools_are_directly_callable():
    registry = ConnectorRegistry()
    registry.register(_FakeConnector())
    lc_tools = registry.as_langchain_tools()
    assert len(lc_tools) == 2
    ping_tool = next(t for t in lc_tools if t.name == "fake.ping")
    assert ping_tool.invoke({"value": 9}) == {"echo": 9}

    boom_tool = next(t for t in lc_tools if t.name == "fake.boom")
    # Errors surface as tool output, not a raised exception, so an LLM
    # agent binding this tool can see and react to the failure.
    assert boom_tool.invoke({"value": 1}) == {"error": "simulated connector failure"}


def test_registry_as_langchain_tools_can_filter_by_connector():
    registry = build_default_registry()
    sap_only = registry.as_langchain_tools(connector_names=["sap"])
    assert {t.name for t in sap_only} == {"sap.fetch_invoice", "sap.fetch_payment_status"}


# ─── Default registry / MCPClient: every real connector wires up ────────

def test_default_registry_has_all_six_connectors():
    registry = build_default_registry()
    assert registry.list_connectors() == sorted(
        ["google_sheets", "slack", "outlook", "jira", "sap", "crm"]
    )


def test_default_registry_exposes_every_required_tool():
    registry = build_default_registry()
    qualified_names = {t.qualified_name for t in registry.list_tools()}
    required = {
        "sap.fetch_invoice",
        "crm.fetch_customer",
        "sap.fetch_payment_status",
        "jira.create_jira_ticket",
        "slack.send_slack_message",
        "outlook.send_email",
        "google_sheets.append_google_sheet",
        "crm.get_customer_history",
    }
    assert required.issubset(qualified_names)


def test_mcp_client_facade_matches_registry():
    client = MCPClient()
    assert len(client.list_tools()) == len(client.registry.list_tools())


# ─── Connector-specific behavior ─────────────────────────────────────────

def test_sap_fetch_invoice_is_deterministic():
    registry = build_default_registry()
    r1 = registry.call_tool("sap.fetch_invoice", {"invoice_no": "INV-777"})
    r2 = registry.call_tool("sap.fetch_invoice", {"invoice_no": "INV-777"})
    assert r1.success and r2.success
    assert r1.result == r2.result


def test_sap_fetch_payment_status_returns_known_status():
    registry = build_default_registry()
    result = registry.call_tool("sap.fetch_payment_status", {"invoice_no": "INV-888"})
    assert result.success
    assert result.result["payment_status"] in {"unpaid", "partially_paid", "overdue", "disputed"}


def test_crm_fetch_customer_is_deterministic():
    registry = build_default_registry()
    r1 = registry.call_tool("crm.fetch_customer", {"client_name": "Acme Corp"})
    r2 = registry.call_tool("crm.fetch_customer", {"client_name": "Acme Corp"})
    assert r1.result == r2.result
    assert r1.result["client_name"] == "Acme Corp"


def test_crm_get_customer_history_uses_real_repository(temp_db):
    """Unlike fetch_customer (mock), get_customer_history is backed by the
    real CustomerMemoryRepository — recording an interaction through the
    repository must be visible through the MCP tool."""
    from database.memory_repository import CustomerMemoryRepository

    registry = build_default_registry()

    unseen = registry.call_tool("crm.get_customer_history", {"client_name": "Brand New Co"})
    assert unseen.result["is_known_client"] is False

    CustomerMemoryRepository().record_interaction("Brand New Co", reminder_sent=True)

    seen = registry.call_tool("crm.get_customer_history", {"client_name": "Brand New Co"})
    assert seen.result["is_known_client"] is True
    assert seen.result["reminders_sent"] == 1


def test_jira_create_ticket_returns_a_ticket_key(tmp_path, monkeypatch):
    import mcp.dry_run_log as dry_run_log_module

    monkeypatch.setattr(dry_run_log_module, "MCP_DRY_RUN_LOG_PATH", tmp_path / "mcp_dry_run.jsonl")
    # jira.py imported MCP_DRY_RUN_LOG_PATH by reference at import time, so
    # patch it there too rather than relying on module-attribute lookup.
    import mcp.connectors.jira as jira_module
    monkeypatch.setattr(jira_module, "MCP_DRY_RUN_LOG_PATH", tmp_path / "mcp_dry_run.jsonl")

    registry = build_default_registry()
    result = registry.call_tool(
        "jira.create_jira_ticket",
        {"summary": "Test", "description": "Test ticket", "priority": "High"},
    )
    assert result.success
    assert result.result["ticket_key"].startswith("FIN-")
    assert result.result["status"] == "Open"


def test_slack_send_message_dry_run_by_default(tmp_path, monkeypatch):
    import mcp.dry_run_log as dry_run_log_module
    monkeypatch.setattr(dry_run_log_module, "MCP_DRY_RUN_LOG_PATH", tmp_path / "mcp_dry_run.jsonl")
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

    registry = build_default_registry()
    result = registry.call_tool("slack.send_slack_message", {"channel": "#test", "message": "hi"})
    assert result.success
    assert result.result["dry_run"] is True


def test_outlook_send_email_reuses_real_email_service(monkeypatch):
    """Confirms the outlook connector is not a separate mock — it produces
    the exact SendResult shape core.email_service.send_email returns."""
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)  # defaults to dry_run

    registry = build_default_registry()
    result = registry.call_tool(
        "outlook.send_email",
        {"to": "a@b.com", "subject": "Test", "body": "Body text", "invoice_no": "INV-1"},
    )
    assert result.success
    assert result.result["provider"] == "dry_run"
    assert result.result["dry_run"] is True


def test_google_sheets_append_dry_run_by_default(monkeypatch, tmp_path):
    import mcp.dry_run_log as dry_run_log_module
    monkeypatch.setattr(dry_run_log_module, "MCP_DRY_RUN_LOG_PATH", tmp_path / "mcp_dry_run.jsonl")
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_JSON", raising=False)

    registry = build_default_registry()
    result = registry.call_tool(
        "google_sheets.append_google_sheet",
        {"spreadsheet_id": "sheet123", "row_values": ["a", "b", "c"]},
    )
    assert result.success
    assert result.result["dry_run"] is True
