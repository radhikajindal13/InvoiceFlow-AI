"""
tests/test_memory.py
------------------------
Deterministic tests for memory/, using MockEmbeddingService (no external
dependency, no network, no LLM). Client names are unique per test
(test-function-scoped prefixes) rather than resetting the process-wide
Qdrant singleton between tests, since agents/coordinator.py holds its own
long-lived MemoryIndex/MemoryRetrieval instances bound to that singleton
from whenever it was first imported in the test session -- unique names
avoid cross-test interference without fighting that shared state.
"""
from memory.conversation_summary import ConversationSummarizer
from memory.customer_profile import CustomerProfileMemory
from memory.index import MemoryIndex
from memory.long_term import LongTermMemory
from memory.retrieval import MemoryRetrieval
from memory.schemas import MemoryType
from memory.short_term import ShortTermMemory


# ─── MemoryIndex / MemoryRetrieval: semantic search ─────────────────────

def test_add_and_search_returns_relevant_record():
    idx = MemoryIndex()
    ret = MemoryRetrieval()

    idx.add_email(
        client_name="SemSearch Client A",
        invoice_no="INV-SS-001",
        text="Sent a warm reminder about invoice payment overdue by 5 days.",
    )
    idx.add_email(
        client_name="SemSearch Client A",
        invoice_no="INV-SS-002",
        text="Discussed unrelated contract renewal terms for next year.",
    )

    results = ret.search(
        query_text="overdue payment reminder",
        client_name="SemSearch Client A",
        limit=1,
    )
    assert len(results) == 1
    assert "overdue" in results[0].record.text.lower()


def test_search_filters_by_client_name():
    idx = MemoryIndex()
    ret = MemoryRetrieval()

    idx.add_email(client_name="Filter Client A", invoice_no="INV-F-1", text="Reminder email content for client A.")
    idx.add_email(client_name="Filter Client B", invoice_no="INV-F-2", text="Reminder email content for client B.")

    results = ret.search(query_text="reminder email", client_name="Filter Client A", limit=10)
    assert all(r.record.client_name == "Filter Client A" for r in results)
    assert len(results) >= 1


def test_search_filters_by_memory_type():
    idx = MemoryIndex()
    ret = MemoryRetrieval()

    idx.add_email(client_name="TypeFilter Client", invoice_no="INV-T-1", text="An email about payment.")
    idx.add_risk_assessment(client_name="TypeFilter Client", invoice_no="INV-T-1", text="A risk assessment about payment.")

    results = ret.search(
        query_text="payment",
        client_name="TypeFilter Client",
        memory_types=[MemoryType.RISK_ASSESSMENT],
        limit=10,
    )
    assert all(r.record.memory_type == MemoryType.RISK_ASSESSMENT for r in results)
    assert len(results) == 1


def test_get_context_for_email_unknown_client_returns_neutral_message():
    ret = MemoryRetrieval()
    context = ret.get_context_for_email(client_name="Never Seen Client XYZ", query_text="anything")
    assert context == "No prior history available for this client."


def test_get_context_for_email_formats_relevant_records():
    idx = MemoryIndex()
    ret = MemoryRetrieval()

    idx.add_email(
        client_name="Context Client",
        invoice_no="INV-C-1",
        text="Sent a firm reminder after the client missed the first deadline.",
    )

    context = ret.get_context_for_email(client_name="Context Client", query_text="reminder deadline missed")
    assert "[Email]" in context
    assert "firm reminder" in context


def test_conversation_summary_upsert_replaces_not_accumulates():
    idx = MemoryIndex()
    id1 = idx.add_conversation_summary(client_name="Summary Client", text="First summary version.")
    id2 = idx.add_conversation_summary(client_name="Summary Client", text="Updated summary version.")
    assert id1 == id2  # same stable ID -> upsert, not a new record

    ret = MemoryRetrieval()
    results = ret.search(
        query_text="summary",
        client_name="Summary Client",
        memory_types=[MemoryType.CONVERSATION_SUMMARY],
        limit=10,
    )
    assert len(results) == 1
    assert results[0].record.text == "Updated summary version."


# ─── ShortTermMemory ──────────────────────────────────────────────────────

def test_short_term_memory_bounded_window():
    stm = ShortTermMemory(window=3)
    for i in range(5):
        stm.add("Client X", f"note {i}")
    recent = stm.get_recent("Client X")
    assert len(recent) == 3
    assert recent == ["note 2", "note 3", "note 4"]


def test_short_term_memory_is_per_client():
    stm = ShortTermMemory()
    stm.add("Client A", "a-note")
    stm.add("Client B", "b-note")
    assert stm.get_recent("Client A") == ["a-note"]
    assert stm.get_recent("Client B") == ["b-note"]


def test_short_term_memory_clear():
    stm = ShortTermMemory()
    stm.add("Client Y", "note")
    stm.clear("Client Y")
    assert stm.get_recent("Client Y") == []


# ─── ConversationSummarizer ────────────────────────────────────────────────

def test_summarizer_unknown_client(temp_db):
    summarizer = ConversationSummarizer()
    summary = summarizer.summarize_client_history("Never Seen Summarizer Client")
    assert "no prior interaction history" in summary.lower()


def test_summarizer_known_client_reflects_real_counters(temp_db):
    from database.memory_repository import CustomerMemoryRepository

    repo = CustomerMemoryRepository()
    repo.record_interaction("Summarizer Known Client", reminder_sent=True, tone_used="Polite but Firm")
    repo.record_interaction("Summarizer Known Client", escalated=True)

    summarizer = ConversationSummarizer()
    summary = summarizer.summarize_client_history("Summarizer Known Client")
    assert "1 reminder" in summary
    assert "escalated 1 time" in summary
    assert "Polite but Firm" in summary


def test_summarizer_refresh_and_store_is_retrievable(temp_db):
    from database.memory_repository import CustomerMemoryRepository

    CustomerMemoryRepository().record_interaction("Refresh Client", reminder_sent=True)
    summarizer = ConversationSummarizer()
    stored_text = summarizer.refresh_and_store("Refresh Client")

    ret = MemoryRetrieval()
    results = ret.search(
        query_text=stored_text,
        client_name="Refresh Client",
        memory_types=[MemoryType.CONVERSATION_SUMMARY],
    )
    assert len(results) == 1
    assert results[0].record.text == stored_text


# ─── CustomerProfileMemory ──────────────────────────────────────────────────

def test_customer_profile_combines_crm_and_counters(temp_db):
    profile_mem = CustomerProfileMemory()
    profile = profile_mem.build_profile("Profile Client Co")

    assert profile["client_name"] == "Profile Client Co"
    assert profile["industry"] is not None  # from mocked CRM connector
    assert profile["reminders_sent"] == 0   # no prior interactions in temp_db
    assert "no prior interaction history" in profile["behavior_summary"].lower()


def test_customer_profile_is_deterministic(temp_db):
    profile_mem = CustomerProfileMemory()
    p1 = profile_mem.build_profile("Deterministic Profile Client")
    p2 = profile_mem.build_profile("Deterministic Profile Client")
    assert p1["industry"] == p2["industry"]
    assert p1["account_manager"] == p2["account_manager"]


# ─── LongTermMemory ─────────────────────────────────────────────────────────

def test_long_term_memory_recall_combines_counters_and_semantic(temp_db):
    from database.memory_repository import CustomerMemoryRepository

    CustomerMemoryRepository().record_interaction("Recall Client", reminder_sent=True)

    idx = MemoryIndex()
    idx.add_email(client_name="Recall Client", invoice_no="INV-R-1", text="Reminder about overdue invoice payment.")

    ltm = LongTermMemory()
    recall = ltm.recall("Recall Client", query_text="overdue invoice payment")

    assert recall["counters"]["reminders_sent"] == 1
    assert len(recall["relevant_memories"]) >= 1
    assert any("overdue" in m["text"].lower() for m in recall["relevant_memories"])


def test_long_term_memory_recall_unknown_client_has_none_counters(temp_db):
    ltm = LongTermMemory()
    recall = ltm.recall("Never Seen Recall Client", query_text="anything")
    assert recall["counters"] is None
