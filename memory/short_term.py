"""
memory/short_term.py
──────────────────────
Short-term memory (brief "MEMORY TYPES" requirement).

Deliberately NOT vector-backed: short-term memory here means "what
happened in the last few turns of this session," which needs to be fast
and process-local, not semantically searched — that's what long-term
memory (memory/long_term.py, Qdrant-backed) is for. A bounded deque per
client, cleared on process restart, is the honest shape of "short-term":
if it needs to survive a restart, it's not short-term anymore, it belongs
in long-term memory or the existing SQL customer_memory table.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque

DEFAULT_WINDOW = 5


class ShortTermMemory:
    def __init__(self, window: int = DEFAULT_WINDOW) -> None:
        self.window = window
        self._lock = threading.Lock()
        self._recent: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=self.window))

    def add(self, client_name: str, note: str) -> None:
        with self._lock:
            self._recent[client_name].append(note)

    def get_recent(self, client_name: str) -> list[str]:
        with self._lock:
            return list(self._recent.get(client_name, []))

    def clear(self, client_name: str) -> None:
        with self._lock:
            self._recent.pop(client_name, None)


# One shared instance per process — same rationale as mcp.client.default_client
# and core.models.model: a single in-memory cache reused everywhere rather
# than each caller holding its own, disconnected window.
default_short_term_memory = ShortTermMemory()
