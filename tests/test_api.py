"""
tests/test_api.py
──────────────────
Exercises the FastAPI layer for real against a temp sqlite DB.

/invoices/generate is tested with a *future* due_date, which is a
genuinely useful edge case: days_overdue == 0 routes to no_overdue_node
(graphs/worker_graph.py), which never touches the LLM, the risk agent, or
the verifier agent — so this test verifies the full API -> worker-graph ->
audit-log wiring end-to-end without needing network access to Mistral.
The overdue/LLM-calling path is documented as out-of-sandbox in
MULTI_AGENT.md and needs a live MISTRAL_API_KEY to exercise.
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(temp_db):
    from api.main import app
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_job_not_found(client):
    resp = client.get("/jobs/9999")
    assert resp.status_code == 404


def test_list_jobs_empty(client):
    resp = client.get("/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_audit_empty(client):
    resp = client.get("/audit")
    assert resp.status_code == 200
    assert resp.json() == []


def test_failed_empty(client):
    resp = client.get("/failed")
    assert resp.status_code == 200
    assert resp.json() == []


def test_retry_nonexistent_failed_invoice(client):
    resp = client.post("/failed/9999/retry")
    assert resp.status_code == 404


def test_customer_history_unknown_client(client):
    resp = client.get("/customers/Nobody%20Inc/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_known_client"] is False


def test_upload_rejects_non_csv(client):
    resp = client.post(
        "/upload",
        files={"file": ("invoices.txt", b"not a csv", "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_rejects_empty_file(client):
    resp = client.post(
        "/upload",
        files={"file": ("invoices.csv", b"", "text/csv")},
    )
    assert resp.status_code == 400


def test_upload_creates_job(client):
    csv_bytes = (
        b"invoice_number,client_name,amount,due_date,recipient_email\n"
        b"INV-API-001,Acme Corp,45000,2026-04-15,accounts@acme.com\n"
    )
    resp = client.post(
        "/upload",
        files={"file": ("invoices.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "started"
    assert isinstance(body["job_id"], int)

    # The job now shows up in the jobs list (background worker may still
    # be running or may have already failed on the real LLM call, since
    # this sandbox has no network access to Mistral — both are fine here,
    # we're only verifying the API <-> upload_handler <-> jobs_repository
    # wiring, not the LLM-dependent pipeline outcome).
    resp = client.get(f"/jobs/{body['job_id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == body["job_id"]


def test_generate_invoice_not_yet_overdue_end_to_end(client):
    """Full API -> worker graph -> audit log path, with no LLM involved,
    because a future due date routes straight through no_overdue_node.

    Uses a "%d %b %Y" date (matching the format used elsewhere in this
    codebase, e.g. graphs/worker_graph.py's __main__ block) rather than
    ISO format: core/utils.py::get_overdue_days calls
    dateutil.parser.parse(..., dayfirst=True), which misparses unambiguous
    ISO 'YYYY-MM-DD' strings whenever the day-of-month is <= 12 (a
    pre-existing quirk unrelated to this phase's MCP work — out of scope
    to fix here since it touches shared, unrelated parsing logic used by
    the whole CSV pipeline)."""
    future_due_date = (date.today() + timedelta(days=10)).strftime("%d %b %Y")

    resp = client.post(
        "/invoices/generate",
        json={
            "invoice_number": "INV-API-002",
            "client_name": "Future Client Ltd",
            "amount": 12000,
            "due_date": future_due_date,
            "recipient_email": "billing@futureclient.com",
        },
    )
    assert resp.status_code == 200
    audit_log = resp.json()
    assert audit_log["invoice_no"] == "INV-API-002"
    assert audit_log["send_status"] == "not_sent"
    assert audit_log["days_overdue"] == 0


def test_mcp_list_tools(client):
    resp = client.get("/mcp/tools")
    assert resp.status_code == 200
    tools = resp.json()
    qualified_names = {t["qualified_name"] for t in tools}
    assert "sap.fetch_invoice" in qualified_names
    assert "crm.get_customer_history" in qualified_names
    # every tool must publish a JSON Schema for its arguments
    sap_tool = next(t for t in tools if t["qualified_name"] == "sap.fetch_invoice")
    assert "invoice_no" in sap_tool["input_schema"]["properties"]


def test_mcp_call_tool_success(client):
    resp = client.post("/mcp/call", json={"tool": "sap.fetch_invoice", "arguments": {"invoice_no": "INV-500"}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["connector"] == "sap"
    assert body["result"]["invoice_no"] == "INV-500"


def test_mcp_call_tool_validation_error(client):
    resp = client.post("/mcp/call", json={"tool": "sap.fetch_invoice", "arguments": {}})
    assert resp.status_code == 200  # validation errors are a normal ToolCallResult, not an HTTP error
    body = resp.json()
    assert body["success"] is False
    assert "validation" in body["error"].lower()


def test_mcp_call_tool_unknown_connector(client):
    resp = client.post("/mcp/call", json={"tool": "nonexistent.tool", "arguments": {}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
