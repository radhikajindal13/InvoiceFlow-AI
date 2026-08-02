"""
memory/conversation_summary.py
─────────────────────────────────
Conversation Summaries (brief "MEMORY TYPES" + "IMPLEMENT" requirement).

Deterministic, template-based by default — no LLM call required, so this
stays testable offline like everything else in this phase. Built from the
same real data sources already in this codebase: the SQL
`customer_memory` counters (database/memory_repository.py, from Phase 1)
plus this invoice's own audit trail (database/audit_repository.py). An
optional LLM-enhanced summary is provided as a clearly separate function
for production use, reusing the existing `core.models.model` instance —
not exercised by tests, same "documented but not live-tested" treatment
already given to the MCP layer's live-credential paths.

Every summary is written back into the vector index as a
CONVERSATION_SUMMARY record (memory/index.py::add_conversation_summary,
stable per-client ID) — so it becomes retrievable context for the *next*
email this client receives, not just a one-off report.
"""

from __future__ import annotations

from typing import Optional

from database.memory_repository import CustomerMemoryRepository
from memory.index import MemoryIndex


class ConversationSummarizer:
    def __init__(self, memory_index: Optional[MemoryIndex] = None) -> None:
        self.memory_index = memory_index or MemoryIndex()
        self._memory_repo = CustomerMemoryRepository()

    def summarize_client_history(self, client_name: str) -> str:
        """Deterministic summary from real counters — no LLM, no network,
        fully reproducible for the same underlying data."""
        summary = self._memory_repo.get_summary(client_name)

        if not summary:
            return f"{client_name} has no prior interaction history with this system."

        parts = [
            f"{client_name} has received {summary['reminders_sent']} reminder(s)"
        ]
        if summary["escalations"]:
            parts.append(f"been escalated {summary['escalations']} time(s)")
        if summary["emails_rejected_in_validation"]:
            parts.append(
                f"had {summary['emails_rejected_in_validation']} generated email(s) "
                "fail validation before sending"
            )
        if summary["last_tone_used"]:
            parts.append(f"most recently addressed with a '{summary['last_tone_used']}' tone")

        return ", ".join(parts) + "."

    def refresh_and_store(self, client_name: str) -> str:
        """Recompute the summary and upsert it into the vector index
        (replacing any prior summary for this client, since
        add_conversation_summary uses a stable per-client ID)."""
        summary_text = self.summarize_client_history(client_name)
        self.memory_index.add_conversation_summary(
            client_name=client_name,
            text=summary_text,
            metadata={"source": "deterministic_template"},
        )
        return summary_text


def summarize_with_llm(client_name: str, raw_history_text: str) -> str:
    """
    Optional LLM-enhanced summary, reusing the existing raw ChatMistralAI
    instance (core.models.model — same one agents/risk_agent.py and
    agents/verifier_agent.py already reuse). Kept separate from the
    deterministic path above so tests never depend on a live model call;
    a caller opts into this explicitly for production-quality prose.
    """
    from core.models import model

    prompt = (
        f"Summarize this client's interaction history in 2-3 sentences, "
        f"focused on payment behavior and tone: \n\n{raw_history_text}"
    )
    response = model.invoke(prompt)
    return response.content if hasattr(response, "content") else str(response)
