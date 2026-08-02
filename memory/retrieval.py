"""
memory/retrieval.py
─────────────────────
Memory Retrieval (brief requirement): the read side of semantic memory,
and the piece that makes RAG (brief's "RAG" section) concrete:

    Search vector database -> Retrieve relevant history -> Inject context
    -> Generate response

`search()` does the first two steps. `get_context_for_email()` does the
third — formats results into a plain-text block that
graphs/worker_graph.py::generate_email_draft injects into the existing
prompt (core/prompts.py) as {relevant_history}, so the fourth step
("Generate response") is the existing, unchanged EMAIL_GENERATION_CHAIN
call, just with better context.
"""

from __future__ import annotations

from typing import Optional

from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from memory.schemas import MemoryRecord, MemoryType, SearchResult
from vectorstore.embeddings import EmbeddingService, get_embedding_service
from vectorstore.qdrant_client import DEFAULT_COLLECTION, ensure_collection, get_qdrant_client


class MemoryRetrieval:
    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        collection_name: str = DEFAULT_COLLECTION,
    ) -> None:
        self.embedding_service = embedding_service or get_embedding_service()
        self.collection_name = collection_name
        self.client = get_qdrant_client()
        ensure_collection(self.client, self.collection_name, self.embedding_service.dimension)

    # ── search ───────────────────────────────────────────────────────────

    def search(
        self,
        query_text: str,
        client_name: Optional[str] = None,
        memory_types: Optional[list[MemoryType]] = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Embed `query_text` and return the top-`limit` most semantically
        similar records, optionally restricted to one client and/or a set
        of memory types via an exact-match Qdrant filter."""
        conditions: list[FieldCondition] = []
        if client_name:
            conditions.append(FieldCondition(key="client_name", match=MatchValue(value=client_name)))
        if memory_types:
            conditions.append(
                FieldCondition(key="memory_type", match=MatchAny(any=[t.value for t in memory_types]))
            )
        query_filter = Filter(must=conditions) if conditions else None

        query_vector = self.embedding_service.embed_text(query_text)
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
        )

        results: list[SearchResult] = []
        for point in response.points:
            record = MemoryRecord.from_payload(point.id, point.payload)
            results.append(SearchResult(record=record, score=point.score))
        return results

    # ── RAG context injection ───────────────────────────────────────────

    def get_context_for_email(
        self,
        client_name: str,
        query_text: str,
        limit: int = 5,
    ) -> str:
        """
        Formats the most relevant prior emails, conversations, risk
        assessments, and approvals for this client into a plain-text block
        ready to inject into the email-generation prompt. Returns a
        neutral "no history" message rather than an empty string when
        nothing relevant is found, so the prompt template always has
        something coherent to show the model.
        """
        results = self.search(
            query_text=query_text,
            client_name=client_name,
            memory_types=[
                MemoryType.EMAIL,
                MemoryType.CONVERSATION,
                MemoryType.RISK_ASSESSMENT,
                MemoryType.APPROVAL,
                MemoryType.CONVERSATION_SUMMARY,
            ],
            limit=limit,
        )

        if not results:
            return "No prior history available for this client."

        lines = []
        for r in results:
            label = r.record.memory_type.value.replace("_", " ").title()
            lines.append(f"- [{label}] {r.record.text}")
        return "\n".join(lines)
