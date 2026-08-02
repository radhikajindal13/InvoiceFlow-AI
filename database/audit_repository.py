from database.db import get_connection


class AuditRepository:
    def save(self, job_id: int, audit_log: dict) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (
                    job_id,
                    invoice_no,
                    client,
                    contact_email_masked,
                    stage_key,
                    tone_used,
                    days_overdue,
                    validation_status,
                    send_status,
                    retry_count,
                    error_message,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, invoice_no, send_status, retry_count)
                DO NOTHING
                """,
                (
                    job_id,
                    audit_log.get("invoice_no"),
                    audit_log.get("client"),
                    audit_log.get("contact_email"),
                    audit_log.get("stage_key"),
                    audit_log.get("tone_used"),
                    audit_log.get("days_overdue"),
                    audit_log.get("validation_status"),
                    audit_log.get("send_status"),
                    audit_log.get("retry_count", 0),
                    audit_log.get("send_error", ""),
                    audit_log.get("timestamp"),
                ),
            )
            conn.commit()

    def get_by_job(self, job_id: int) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_logs WHERE job_id = ? ORDER BY id",
                (job_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_by_invoice_no(self, invoice_no: str, limit: int = 10) -> list[dict]:
        """
        All prior audit entries for this invoice number across every job
        (an invoice can appear in a retried upload, a scheduler retry, etc).
        Used by agents/tools.py::fetch_invoice_history so agents can see
        whether this invoice has already been through follow-ups, rejections,
        or escalations instead of reasoning about it in a vacuum.
        """
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM audit_logs
                WHERE invoice_no = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (invoice_no, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_recent(self, limit: int = 100) -> list[dict]:
        """Global audit feed across all jobs, most recent first — used by
        the API's GET /audit endpoint when no job_id filter is given."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]