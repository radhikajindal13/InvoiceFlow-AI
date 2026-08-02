"""
tests/test_vectorstore.py
----------------------------
No external dependency needed: MockEmbeddingService is deterministic and
offline, and Qdrant runs in embedded ":memory:" mode (a real qdrant-client
engine, just not talking to a server) -- see vectorstore/qdrant_client.py.
"""
from vectorstore.embeddings import MockEmbeddingService, get_embedding_service
from vectorstore.qdrant_client import (
    DEFAULT_COLLECTION,
    ensure_collection,
    get_qdrant_client,
    reset_qdrant_client,
)


def test_mock_embedding_is_deterministic():
    emb = MockEmbeddingService()
    v1 = emb.embed_text("Invoice INV-1 overdue payment reminder")
    v2 = emb.embed_text("Invoice INV-1 overdue payment reminder")
    assert v1 == v2


def test_mock_embedding_normalizes_whitespace_and_case():
    emb = MockEmbeddingService()
    v1 = emb.embed_text("Hello   World")
    v2 = emb.embed_text("hello world")
    assert v1 == v2


def test_mock_embedding_differentiates_unrelated_text():
    emb = MockEmbeddingService()
    v1 = emb.embed_text("Overdue invoice payment reminder for Acme Corp")
    v2 = emb.embed_text("The weather today is sunny with a chance of rain")

    def cosine(a, b):
        return sum(x * y for x, y in zip(a, b))

    assert cosine(v1, v1) > 0.99  # identical text: ~1.0
    assert cosine(v1, v2) < 0.5   # unrelated text: much lower


def test_mock_embedding_has_expected_dimension():
    emb = MockEmbeddingService()
    v = emb.embed_text("x")
    assert len(v) == emb.dimension


def test_get_embedding_service_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    svc = get_embedding_service()
    assert isinstance(svc, MockEmbeddingService)


def test_get_embedding_service_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "not_a_real_provider")
    try:
        get_embedding_service()
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_qdrant_client_is_a_process_singleton():
    reset_qdrant_client()
    c1 = get_qdrant_client()
    c2 = get_qdrant_client()
    assert c1 is c2
    reset_qdrant_client()


def test_ensure_collection_is_idempotent():
    reset_qdrant_client()
    client = get_qdrant_client()
    ensure_collection(client, DEFAULT_COLLECTION, vector_size=8)
    ensure_collection(client, DEFAULT_COLLECTION, vector_size=8)  # must not raise
    assert client.collection_exists(DEFAULT_COLLECTION)
    reset_qdrant_client()
