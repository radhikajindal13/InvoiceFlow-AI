"""
memory/index.py
─────────────────
Memory Index (brief requirement): the write side of semantic memory.
Embeds a record's text and upserts it into Qdrant with its metadata as
payload. One typed `add_*` method per thing this system stores (brief's
"STORE" section): invoice history, emails, customer conversations, risk
assessments, approval history — each just calls the generic `add()` with
the right MemoryType and a formatted text blob.
"""

from __future__ import annotations

from typing import Any, Optional

from qdrant_client.models import PointStruct

from memory.schemas import MemoryRecord, MemoryType
from vectorstore.embeddings import EmbeddingService, get_embedding_service
from vectorstore.qdrant_client import DEFAULT_COLLECTION, ensure_collection, get_qdrant_client


class MemoryIndex:
    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        collection_name: str = DEFAULT_COLLECTION,
    ) -> None:
        self.embedding_service = embedding_service or get_embedding_service()
        self.collection_name = collection_name
        self.client = get_qdrant_client()
        ensure_collection(self.client, self.collection_name, self.embedding_service.dimension)

    # ── generic write ────────────────────────────────────────────────────

    def add(self, record: MemoryRecord) -> str:
        vector = self.embedding_service.embed_text(record.text)
        self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=record.id, vector=vector, payload=record.to_payload())],
        )
        return record.id

    # ── typed helpers (brief "STORE" section) ───────────────────────────

    def add_invoice_history(
        self, client_name: str, invoice_no: str, text: str, metadata: Optional[dict[str, Any]] = None
    ) -> str:
        return self.add(MemoryRecord(
            memory_type=MemoryType.INVOICE_HISTORY,
            text=text, client_name=client_name, invoice_no=invoice_no,
            metadata=metadata or {},
        ))

    def add_email(
        self, client_name: str, invoice_no: str, text: str, metadata: Optional[dict[str, Any]] = None
    ) -> str:
        return self.add(MemoryRecord(
            memory_type=MemoryType.EMAIL,
            text=text, client_name=client_name, invoice_no=invoice_no,
            metadata=metadata or {},
        ))

    def add_conversation(
        self, client_name: str, text: str, invoice_no: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        return self.add(MemoryRecord(
            memory_type=MemoryType.CONVERSATION,
            text=text, client_name=client_name, invoice_no=invoice_no,
            metadata=metadata or {},
        ))

    def add_risk_assessment(
        self, client_name: str, invoice_no: str, text: str, metadata: Optional[dict[str, Any]] = None
    ) -> str:
        return self.add(MemoryRecord(
            memory_type=MemoryType.RISK_ASSESSMENT,
            text=text, client_name=client_name, invoice_no=invoice_no,
            metadata=metadata or {},
        ))

    def add_approval(
        self, client_name: str, invoice_no: str, text: str, metadata: Optional[dict[str, Any]] = None
    ) -> str:
        return self.add(MemoryRecord(
            memory_type=MemoryType.APPROVAL,
            text=text, client_name=client_name, invoice_no=invoice_no,
            metadata=metadata or {},
        ))

    def add_conversation_summary(
        self, client_name: str, text: str, metadata: Optional[dict[str, Any]] = None
    ) -> str:
        """Conversation summaries are upserted under a stable, deterministic
        ID (per client) rather than a fresh uuid each time, so refreshing a
        client's summary replaces the old one instead of accumulating an
        ever-growing pile of stale summaries."""
        record = MemoryRecord(
            memory_type=MemoryType.CONVERSATION_SUMMARY,
            text=text, client_name=client_name,
            metadata=metadata or {},
            id=_deterministic_id("summary", client_name),
        )
        return self.add(record)

    def add_customer_profile(
        self, client_name: str, text: str, metadata: Optional[dict[str, Any]] = None
    ) -> str:
        """Same stable-ID-per-client approach as conversation summaries —
        a customer profile is a single living document, not a growing log."""
        record = MemoryRecord(
            memory_type=MemoryType.CUSTOMER_PROFILE,
            text=text, client_name=client_name,
            metadata=metadata or {},
            id=_deterministic_id("profile", client_name),
        )
        return self.add(record)


def _deterministic_id(kind: str, client_name: str) -> str:
    import uuid as _uuid
    return str(_uuid.uuid5(_uuid.NAMESPACE_DNS, f"{kind}:{client_name.strip().lower()}"))
