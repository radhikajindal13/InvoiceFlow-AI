"""
vectorstore/qdrant_client.py
──────────────────────────────
Qdrant Client (brief requirement).

Defaults to Qdrant's embedded in-memory mode (`QdrantClient(":memory:")`)
— a real Qdrant engine, not a fake/mocked one, just running in-process
instead of against a server. That's what makes this genuinely testable
with zero external dependencies: the same real `qdrant-client` library
runs identically against a real server in production (set QDRANT_URL) or
in-memory here, with no code branching between the two.
"""

from __future__ import annotations

import os
import threading

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

DEFAULT_COLLECTION = "agent_memory"

_client_lock = threading.Lock()
_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    """
    Process-wide singleton so every caller (MemoryIndex, MemoryRetrieval,
    tests) shares one in-memory collection instead of each spinning up an
    isolated `:memory:` instance that can't see the others' data.

    QDRANT_URL unset/":memory:"  -> embedded, in-process, no server
    QDRANT_URL="http://host:6333" -> real Qdrant server
    """
    global _client
    with _client_lock:
        if _client is None:
            location = os.getenv("QDRANT_URL", ":memory:").strip()
            if location in ("", ":memory:"):
                _client = QdrantClient(location=":memory:")
            else:
                _client = QdrantClient(url=location)
        return _client


def reset_qdrant_client() -> None:
    """Test-only: drop the singleton so the next get_qdrant_client() call
    starts a fresh in-memory instance (empty collections)."""
    global _client
    with _client_lock:
        _client = None


def ensure_collection(
    client: QdrantClient,
    collection_name: str,
    vector_size: int,
    distance: Distance = Distance.COSINE,
) -> None:
    """Idempotent collection creation — safe to call on every startup."""
    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=distance),
        )
