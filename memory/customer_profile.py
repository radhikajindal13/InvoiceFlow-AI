"""
memory/customer_profile.py
-----------------------------
Customer Profile memory (brief "MEMORY TYPES" requirement).

Deliberately a thin composition layer, not a new data source: pulls
together three things that already exist elsewhere in this codebase --

    mcp.client.default_client -> crm.fetch_customer   (mock CRM profile,
                                  Phase 3: industry, account tier, rep)
    database/memory_repository.py -> CustomerMemoryRepository
                                  (real counters, Phase 1: reminders,
                                  escalations, rejections)
    memory/conversation_summary.py -> ConversationSummarizer
                                  (real, deterministic prose summary)

-- into one profile record, both as a plain dict (for direct use) and as
a text blob (for storage as a CUSTOMER_PROFILE memory in Qdrant, so it's
itself semantically retrievable, e.g. "find clients similar to a slow
payer in manufacturing").
"""

from __future__ import annotations

from typing import Optional

from database.memory_repository import CustomerMemoryRepository
from mcp.client import default_client
from memory.conversation_summary import ConversationSummarizer
from memory.index import MemoryIndex


class CustomerProfileMemory:
    def __init__(self, memory_index: Optional[MemoryIndex] = None) -> None:
        self.memory_index = memory_index or MemoryIndex()
        self._memory_repo = CustomerMemoryRepository()
        self._summarizer = ConversationSummarizer(memory_index=self.memory_index)

    def build_profile(self, client_name: str) -> dict:
        crm_result = default_client.call_tool("crm.fetch_customer", {"client_name": client_name})
        crm_profile = crm_result.result if crm_result.success else {}

        counters = self._memory_repo.get_summary(client_name) or {
            "reminders_sent": 0, "escalations": 0, "emails_rejected_in_validation": 0,
        }
        summary_text = self._summarizer.summarize_client_history(client_name)

        return {
            "client_name": client_name,
            "industry": crm_profile.get("industry"),
            "account_tier": crm_profile.get("account_tier"),
            "account_manager": crm_profile.get("account_manager"),
            "reminders_sent": counters["reminders_sent"],
            "escalations": counters["escalations"],
            "emails_rejected_in_validation": counters["emails_rejected_in_validation"],
            "behavior_summary": summary_text,
        }

    def build_profile_text(self, client_name: str) -> str:
        profile = self.build_profile(client_name)
        pieces = [f"{profile['client_name']} is a {profile.get('account_tier', 'Standard')} tier client"]
        if profile.get("industry"):
            pieces.append(f"in the {profile['industry']} industry")
        pieces.append(f"managed by {profile.get('account_manager', 'an unassigned rep')}")
        return ", ".join(pieces) + f". {profile['behavior_summary']}"

    def refresh_and_store(self, client_name: str) -> str:
        """Recompute the profile and upsert it into the vector index
        (stable per-client ID, same pattern as conversation summaries)."""
        profile_text = self.build_profile_text(client_name)
        self.memory_index.add_customer_profile(
            client_name=client_name,
            text=profile_text,
            metadata={"source": "crm_mock+sql_counters+summary"},
        )
        return profile_text
