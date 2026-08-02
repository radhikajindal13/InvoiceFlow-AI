"""
memory/schemas.py
────────────────────
Shared data shapes for the memory/ package. One Qdrant collection
(vectorstore.DEFAULT_COLLECTION) holds every memory type below,
disambiguated by the `memory_type` payload field — simpler to query
across types (e.g. "everything about Acme Corp regardless of type") than
five separate collections, at the cost of needing a payload filter when
you want just one type. Both memory/index.py and memory/retrieval.py
filter by memory_type when that's what's wanted.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class MemoryType(str, Enum):
    INVOICE_HISTORY = "invoice_history"
    EMAIL = "email"
    CONVERSATION = "conversation"
    RISK_ASSESSMENT = "risk_assessment"
    APPROVAL = "approval"
    CONVERSATION_SUMMARY = "conversation_summary"
    CUSTOMER_PROFILE = "customer_profile"


@dataclass
class MemoryRecord:
    """One thing worth remembering: an email that was sent, a risk
    assessment that was made, a conversation summary, etc. `text` is what
    gets embedded and semantically searched; `metadata` is exact-match
    payload (client_name, invoice_no, ...) usable as a Qdrant filter."""

    memory_type: MemoryType
    text: str
    client_name: str
    invoice_no: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_payload(self) -> dict[str, Any]:
        return {
            "memory_type": self.memory_type.value,
            "text": self.text,
            "client_name": self.client_name,
            "invoice_no": self.invoice_no,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_payload(cls, point_id: str, payload: dict[str, Any]) -> "MemoryRecord":
        return cls(
            id=str(point_id),
            memory_type=MemoryType(payload["memory_type"]),
            text=payload["text"],
            client_name=payload["client_name"],
            invoice_no=payload.get("invoice_no"),
            metadata=payload.get("metadata", {}),
            created_at=payload.get("created_at", ""),
        )


@dataclass
class SearchResult:
    record: MemoryRecord
    score: float
