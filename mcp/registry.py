"""
mcp/registry.py
─────────────────
Connector Registry (brief requirement) + Tool Discovery.

Holds every registered connector and answers two questions for the whole
system at once, regardless of how many connectors exist:

    "what tools are available?"   -> list_tools()   (discovery)
    "run this one, with these args" -> call_tool()   (execution, by
                                        qualified_name so ambiguity is
                                        impossible)

Adding a future connector (brief requirement: "should allow adding future
connectors without changing the coordinator") means writing a new
BaseConnector subclass and one `registry.register(...)` call in
mcp/client.py — nothing in agents/coordinator.py, graphs/worker_graph.py,
or any other connector needs to change, because they only ever go through
this registry, never import a connector module directly.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import StructuredTool

from mcp.connector import BaseConnector
from mcp.protocol import ToolCallResult, ToolSpec

logger = logging.getLogger("mcp")


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, BaseConnector] = {}

    # ── lifecycle ────────────────────────────────────────────────────────

    def register(self, connector: BaseConnector) -> None:
        if connector.connector_name in self._connectors:
            raise ValueError(f"Connector '{connector.connector_name}' is already registered")
        self._connectors[connector.connector_name] = connector
        logger.info(
            "mcp.connector_registered name=%s tools=%s",
            connector.connector_name,
            [t.name for t in connector.list_tools()],
        )

    def unregister(self, connector_name: str) -> None:
        self._connectors.pop(connector_name, None)

    def get_connector(self, connector_name: str) -> Optional[BaseConnector]:
        return self._connectors.get(connector_name)

    def list_connectors(self) -> list[str]:
        return sorted(self._connectors.keys())

    # ── discovery ────────────────────────────────────────────────────────

    def list_tools(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for connector in self._connectors.values():
            specs.extend(connector.list_tools())
        return specs

    # ── execution ────────────────────────────────────────────────────────

    def call_tool(self, qualified_name: str, arguments: dict[str, Any]) -> ToolCallResult:
        if "." not in qualified_name:
            return ToolCallResult(
                tool=qualified_name,
                connector="unknown",
                success=False,
                error=(
                    f"'{qualified_name}' is not a qualified tool name "
                    "(expected 'connector.tool', e.g. 'sap.fetch_invoice')"
                ),
            )

        connector_name, tool_name = qualified_name.split(".", 1)
        connector = self.get_connector(connector_name)
        if connector is None:
            return ToolCallResult(
                tool=tool_name,
                connector=connector_name,
                success=False,
                error=f"No connector registered as '{connector_name}'. "
                      f"Known connectors: {self.list_connectors()}",
            )
        return connector.call_tool(tool_name, arguments)

    # ── LangChain bridge ─────────────────────────────────────────────────

    def as_langchain_tools(self, connector_names: Optional[list[str]] = None) -> list[StructuredTool]:
        """
        Convert every registered MCP tool (or just the given connectors'
        tools) into real `StructuredTool` objects that a LangChain agent
        can `.bind_tools([...])` directly — the same tool-calling loop
        already built in agents/base.py works unmodified against MCP
        tools, since from the agent's point of view they're indistinguishable
        from any other LangChain tool.
        """
        lc_tools: list[StructuredTool] = []
        for connector in self._connectors.values():
            if connector_names and connector.connector_name not in connector_names:
                continue
            for spec in connector.list_tools():
                lc_tools.append(self._make_langchain_tool(connector, spec))
        return lc_tools

    def _make_langchain_tool(self, connector: BaseConnector, spec: ToolSpec) -> StructuredTool:
        args_schema = connector.get_schema(spec.name)

        def _run(**kwargs: Any) -> Any:
            call_result = connector.call_tool(spec.name, kwargs)
            if not call_result.success:
                # Surface errors as tool output (not a raised exception) so
                # a tool-calling LLM can see the failure and react to it,
                # exactly like the "error handling" requirement calls for.
                return {"error": call_result.error}
            return call_result.result

        return StructuredTool.from_function(
            func=_run,
            name=spec.qualified_name,
            description=spec.description,
            args_schema=args_schema,
        )
