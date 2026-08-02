"""
mcp/protocol.py
────────────────
Protocol-level data structures for this project's MCP integration.

Modeled on the two calls that matter in the real Model Context Protocol
spec — `tools/list` (discovery) and `tools/call` (execution) — kept as
plain dataclasses rather than a full JSON-RPC transport. See MCP.md
("Why in-process, not a JSON-RPC transport") for why: the Connector
interface below is transport-agnostic, so a real stdio/HTTP JSON-RPC
transport can be dropped in later without touching connector code.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ToolSpec:
    """
    Describes one callable tool, equivalent to one entry in a real MCP
    server's `tools/list` response: name, human-readable description, and
    a JSON Schema for its arguments (so a client — human, LangChain agent,
    or otherwise — knows how to call it without reading connector source).
    """
    name: str                       # unqualified, e.g. "fetch_invoice"
    connector: str                  # e.g. "sap"
    description: str
    input_schema: dict[str, Any]    # JSON Schema, from a Pydantic model

    @property
    def qualified_name(self) -> str:
        """Namespaced name used for discovery/execution across connectors,
        e.g. "sap.fetch_invoice" — prevents collisions if two connectors
        ever expose a tool with the same short name."""
        return f"{self.connector}.{self.name}"


@dataclass
class ToolCallResult:
    """Equivalent to a real MCP server's `tools/call` response, plus the
    bookkeeping (timing, connector/tool identity) the tool execution layer
    needs for logging."""
    tool: str
    connector: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    called_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "connector": self.connector,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }
