from agents.tools import calculate_risk_score, verify_email_facts, lookup_customer_history, fetch_invoice_history
from database.memory_repository import CustomerMemoryRepository
from database.audit_repository import AuditRepository


def test_calculate_risk_score_low_for_fresh_small_invoice():
    result = calculate_risk_score.invoke({"days_overdue": 2, "amount": 5000})
    assert result["band"] == "low"
    assert 0 <= result["score"] < 25


def test_calculate_risk_score_critical_for_repeat_offender():
    result = calculate_risk_score.invoke({
        "days_overdue": 45,
        "amount": 400_000,
        "prior_escalations": 3,
        "prior_rejections": 4,
        "invoice_attempt_count": 3,
    })
    assert result["band"] == "critical"
    assert result["score"] >= 75


def test_calculate_risk_score_is_deterministic():
    args = {"days_overdue": 20, "amount": 75_000, "prior_escalations": 1}
    r1 = calculate_risk_score.invoke(args)
    r2 = calculate_risk_score.invoke(args)
    assert r1 == r2


def test_verify_email_facts_all_present():
    body = (
        "Hi Acme Corp Team, Invoice #INV-001 for INR 45,250.75 is 10 days "
        "overdue. Pay here: https://pay.company.com/INV-001. Regards."
    )
    result = verify_email_facts.invoke({
        "body_text": body,
        "invoice_no": "INV-001",
        "client_name": "Acme Corp",
        "days_overdue": 10,
        "payment_link": "https://pay.company.com/INV-001",
        "amount_display": "INR 45,250.75",
    })
    assert result["all_facts_present"] is True
    assert result["missing_facts"] == []


def test_verify_email_facts_catches_missing_invoice_number():
    body = "Hi Acme Corp Team, your invoice is overdue. Please pay soon. Regards."
    result = verify_email_facts.invoke({
        "body_text": body,
        "invoice_no": "INV-001",
        "client_name": "Acme Corp",
        "days_overdue": 10,
        "payment_link": "https://pay.company.com/INV-001",
        "amount_display": "INR 45,250.75",
    })
    assert result["all_facts_present"] is False
    assert "invoice_no" in result["missing_facts"]
    assert "payment_link" in result["missing_facts"]


def test_lookup_customer_history_unknown_client(temp_db):
    result = lookup_customer_history.invoke({"client_name": "Nobody Inc"})
    assert result["is_known_client"] is False
    assert result["reminders_sent"] == 0


def test_lookup_customer_history_after_recording(temp_db):
    repo = CustomerMemoryRepository()
    repo.record_interaction("Acme Corp", reminder_sent=True, tone_used="Warm & Friendly")
    repo.record_interaction("Acme Corp", escalated=True)

    result = lookup_customer_history.invoke({"client_name": "Acme Corp"})
    assert result["is_known_client"] is True
    assert result["reminders_sent"] == 1
    assert result["escalations"] == 1
    assert result["last_tone_used"] == "Warm & Friendly"


def test_fetch_invoice_history_empty(temp_db):
    result = fetch_invoice_history.invoke({"invoice_no": "INV-999"})
    assert result["attempt_count"] == 0


def test_fetch_invoice_history_after_audit_save(temp_db):
    from database.jobs_repository import JobsRepository

    job_id = JobsRepository().create_job(file_path="x.csv", file_hash="hash123")

    repo = AuditRepository()
    repo.save(job_id=job_id, audit_log={
        "invoice_no": "INV-002",
        "client": "Acme Corp",
        "contact_email": "a@acme.com",
        "stage_key": "1st Follow-Up",
        "tone_used": "Warm & Friendly",
        "days_overdue": 3,
        "validation_status": "approved",
        "send_status": "sent",
        "retry_count": 0,
        "send_error": "",
        "timestamp": "2026-01-01T00:00:00Z",
    })
    result = fetch_invoice_history.invoke({"invoice_no": "INV-002"})
    assert result["attempt_count"] == 1
    assert result["attempts"][0]["send_status"] == "sent"
