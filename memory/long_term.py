"""
memory/long_term.py
----------------------
Long-term memory (brief "MEMORY TYPES" requirement).

This system now has two long-term memory layers, and this module is
where they meet rather than compete:

    database/memory_repository.py -> structured, exact counters
                                      (reminders_sent, escalations, ...)
                                      Phase 1. Cheap, exact, not
                                      semantically searchable.
    memory/index.py + retrieval.py -> semantic, embedded records
                                      (actual email text, risk reasoning,
                                      conversation summaries). Phase 4
                                      (this phase). Fuzzy, similarity-
                                      ranked, captures content the
                                      counters can't.

`LongTermMemory.recall()` is the one method that answers "what do we
know about this client" using both: exact counters for the numbers,
semantic search for the relevant narrative context.
"""

from __future__ import annotations

from typing import Optional

from database.memory_repository import CustomerMemoryRepository
from memory.retrieval import MemoryRetrieval
from memory.schemas import SearchResult


class LongTermMemory:
    def __init__(self, retrieval: Optional[MemoryRetrieval] = None) -> None:
        self.retrieval = retrieval or MemoryRetrieval()
        self._memory_repo = CustomerMemoryRepository()

    def recall(self, client_name: str, query_text: str, limit: int = 5) -> dict:
        """Combines exact structured counters with semantically relevant
        historical records for a client, given a query (e.g. the invoice
        currently being processed)."""
        counters = self._memory_repo.get_summary(client_name)
        relevant: list[SearchResult] = self.retrieval.search(
            query_text=query_text, client_name=client_name, limit=limit
        )
        return {
            "client_name": client_name,
            "counters": counters,
            "relevant_memories": [
                {"type": r.record.memory_type.value, "text": r.record.text, "score": r.score}
                for r in relevant
            ],
        }
