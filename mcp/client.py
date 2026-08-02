"""
mcp/client.py
───────────────
Base MCP Client (brief requirement): "the AI agent should become an MCP
client." This module is the one place that knows about every concrete
connector — nowhere else in the codebase imports a connector module
directly. Agents, the coordinator, and API routes all go through
`MCPClient` (or the module-level `default_client`), so adding a seventh
connector later is a two-line change here and nowhere else.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import StructuredTool

from mcp.connectors.crm import CrmConnector
from mcp.connectors.google_sheets import GoogleSheetsConnector
from mcp.connectors.jira import JiraConnector
from mcp.connectors.outlook import OutlookConnector
from mcp.connectors.sap import SapConnector
from mcp.connectors.slack import SlackConnector
from mcp.protocol import ToolCallResult, ToolSpec
from mcp.registry import ConnectorRegistry

logger = logging.getLogger("mcp")


def build_default_registry() -> ConnectorRegistry:
    """
    Every connector this platform currently knows about, registered once.
    To add a connector: write a BaseConnector subclass under
    mcp/connectors/, then add one `registry.register(...)` line here.
    Nothing outside this function needs to change (see MCP.md § Adding a
    new connector).
    """
    registry = ConnectorRegistry()
    registry.register(GoogleSheetsConnector())
    registry.register(SlackConnector())
    registry.register(OutlookConnector())
    registry.register(JiraConnector())
    registry.register(SapConnector())
    registry.register(CrmConnector())
    return registry


class MCPClient:
    """Thin, stateless-except-for-the-registry facade. Kept intentionally
    small: list tools, call a tool, or get LangChain-bindable tools —
    everything else lives in the registry/connector layer."""

    def __init__(self, registry: Optional[ConnectorRegistry] = None) -> None:
        self.registry = registry or build_default_registry()

    def list_tools(self) -> list[ToolSpec]:
        return self.registry.list_tools()

    def call_tool(self, qualified_name: str, arguments: dict[str, Any]) -> ToolCallResult:
        return self.registry.call_tool(qualified_name, arguments)

    def as_langchain_tools(self, connector_names: Optional[list[str]] = None) -> list[StructuredTool]:
        return self.registry.as_langchain_tools(connector_names)


# A single shared client, analogous to core/models.py's module-level
# `model` instance — one MCP client for the whole process, reused
# everywhere instead of re-registering connectors on every call.
default_client = MCPClient()
