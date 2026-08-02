"""
vectorstore/embeddings.py
────────────────────────────
Embedding Service (brief requirement).

Same "safe by default, pluggable to a real provider" pattern already used
throughout this project — EMAIL_PROVIDER (core/email_service.py),
SLACK_WEBHOOK_URL (mcp/connectors/slack.py), GOOGLE_SHEETS_CREDENTIALS_JSON
(mcp/connectors/google_sheets.py) — applied here as EMBEDDING_PROVIDER:

    EMBEDDING_PROVIDER=mock     (default) — deterministic, offline, no
                                 network call, no API key. Same text always
                                 produces the same vector, which is exactly
                                 what makes tests/test_vectorstore.py
                                 possible without any external dependency.
    EMBEDDING_PROVIDER=mistral — real embeddings via langchain_mistralai,
                                 for actual semantic quality in production.
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod

MOCK_EMBEDDING_DIM = 256


class EmbeddingService(ABC):
    dimension: int

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


class MockEmbeddingService(EmbeddingService):
    """
    Deterministic, offline embedding: hashes the text with a rolling set
    of salts to fill a fixed-size vector, then L2-normalizes it so cosine
    similarity behaves sensibly. Not semantically meaningful the way a
    real embedding model is — but genuinely deterministic (same text same
    vector, every time, every process) and genuinely differentiates
    unrelated text (different text -> different vector), which is exactly
    what the test suite needs to verify semantic search actually ranks
    results, without hitting any embedding API.
    """

    dimension = MOCK_EMBEDDING_DIM

    def embed_text(self, text: str) -> list[float]:
        normalized = " ".join(text.lower().split())
        vector: list[float] = []
        salt = 0
        while len(vector) < self.dimension:
            digest = hashlib.sha256(f"{salt}:{normalized}".encode("utf-8")).digest()
            # 32 bytes -> 32 floats in [-1, 1) per salt round
            vector.extend((b / 128.0) - 1.0 for b in digest)
            salt += 1
        vector = vector[: self.dimension]

        norm = sum(v * v for v in vector) ** 0.5
        if norm == 0:
            return vector
        return [v / norm for v in vector]


class MistralEmbeddingService(EmbeddingService):
    """Real embeddings via Mistral's embedding API. Not exercised in this
    sandbox (no network access to api.mistral.ai) — implemented for a
    real deployment with MISTRAL_API_KEY set."""

    dimension = 1024  # mistral-embed's native dimension

    def __init__(self) -> None:
        from langchain_mistralai import MistralAIEmbeddings

        self._client = MistralAIEmbeddings(model="mistral-embed")

    def embed_text(self, text: str) -> list[float]:
        return self._client.embed_query(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._client.embed_documents(texts)


def get_embedding_service() -> EmbeddingService:
    provider = os.getenv("EMBEDDING_PROVIDER", "mock").lower().strip()
    if provider == "mock":
        return MockEmbeddingService()
    if provider == "mistral":
        return MistralEmbeddingService()
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: '{provider}' (expected 'mock' or 'mistral')")
