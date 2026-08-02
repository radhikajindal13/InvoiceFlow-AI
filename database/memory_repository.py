"""
database/memory_repository.py
──────────────────────────────
Persistent, cross-job customer memory.

Follows the exact same pattern as audit_repository.py / jobs_repository.py
(raw sqlite3 via get_connection(), parameterized queries, atomic commits)
so it drops into the existing repository layer instead of introducing a
second data-access style.
"""

from datetime import datetime, timezone
from typing import Optional

from database.db import get_connection


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CustomerMemoryRepository:
    def get_summary(self, client_name: str) -> Optional[dict]:
        """Return the stored memory row for a client, or None if unseen."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM customer_memory WHERE client_name = ?",
                (client_name,),
            ).fetchone()
            return dict(row) if row else None

    def record_interaction(
        self,
        client_name: str,
        *,
        reminder_sent: bool = False,
        escalated: bool = False,
        validation_rejected: bool = False,
        tone_used: Optional[str] = None,
    ) -> None:
        """
        Upsert a client's behavioral counters. Called once per invoice
        outcome (from the worker graph's auditLog node) so memory always
        reflects what actually happened, not a prediction.
        """
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO customer_memory (
                    client_name, reminders_sent, escalations,
                    emails_rejected_in_validation, last_tone_used,
                    last_interaction_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_name) DO UPDATE SET
                    reminders_sent = reminders_sent + excluded.reminders_sent,
                    escalations = escalations + excluded.escalations,
                    emails_rejected_in_validation =
                        emails_rejected_in_validation
                        + excluded.emails_rejected_in_validation,
                    last_tone_used = COALESCE(excluded.last_tone_used, last_tone_used),
                    last_interaction_at = excluded.last_interaction_at
                """,
                (
                    client_name,
                    1 if reminder_sent else 0,
                    1 if escalated else 0,
                    1 if validation_rejected else 0,
                    tone_used,
                    utc_now(),
                ),
            )
            conn.commit()
