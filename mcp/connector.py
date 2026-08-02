"""
mcp/connector.py
──────────────────
Generic Connector Interface (brief requirement).

Every connector (Google Sheets, Slack, Outlook, Jira, SAP, CRM, and any
future one) subclasses `BaseConnector` and registers its tools with
`@self.tool(...)` in `__init__`. `BaseConnector.call_tool()` — inherited,
never overridden by subclasses — is the single place that does:

    1. look up the tool by name
    2. validate arguments against its Pydantic schema
    3. log the call (request, and result or error)
    4. execute it, catching any exception so a connector bug never crashes
       the coordinator — it comes back as a normal ToolCallResult(success=False)

This is what satisfies "every tool must contain schema, validation,
logging, error handling" without every connector re-implementing those
four things — they get them for free by using `@self.tool`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from pydantic import BaseModel, ValidationError

from mcp.protocol import ToolCallResult, ToolSpec

logger = logging.getLogger("mcp")


@dataclass
class _RegisteredTool:
    name: str
    description: str
    args_schema: type[BaseModel]
    handler: Callable[..., Any]


class BaseConnector:
    """
    Subclass this, set `connector_name`, and register tools in __init__:

        class SapConnector(BaseConnector):
            connector_name = "sap"

            def __init__(self):
                super().__init__()
                self.tool(
                    name="fetch_invoice",
                    description="...",
                    args_schema=FetchInvoiceArgs,
                )(self._fetch_invoice)

            def _fetch_invoice(self, invoice_no: str) -> dict:
                ...
    """

    connector_name: str = "unnamed_connector"

    def __init__(self) -> None:
        self._tools: dict[str, _RegisteredTool] = {}

    # ── registration ─────────────────────────────────────────────────────

    def tool(self, name: str, description: str, args_schema: type[BaseModel]):
        """Decorator: registers `handler` as a callable tool with a name,
        description, and a Pydantic argument schema for validation."""

        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            self._tools[name] = _RegisteredTool(
                name=name,
                description=description,
                args_schema=args_schema,
                handler=handler,
            )
            return handler

        return decorator

    # ── discovery ────────────────────────────────────────────────────────

    def list_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name=t.name,
                connector=self.connector_name,
                description=t.description,
                input_schema=t.args_schema.model_json_schema(),
            )
            for t in self._tools.values()
        ]

    # ── execution ────────────────────────────────────────────────────────

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolCallResult:
        started = time.perf_counter()
        registered = self._tools.get(tool_name)

        if registered is None:
            logger.error("mcp.tool_not_found connector=%s tool=%s", self.connector_name, tool_name)
            return ToolCallResult(
                tool=tool_name,
                connector=self.connector_name,
                success=False,
                error=f"Tool '{tool_name}' not found on connector '{self.connector_name}'",
            )

        logger.info(
            "mcp.tool_call.start connector=%s tool=%s args=%s",
            self.connector_name, tool_name, arguments,
        )

        # 1. Validation — reject bad arguments before the handler ever runs.
        try:
            validated = registered.args_schema(**arguments)
        except ValidationError as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.warning(
                "mcp.tool_call.validation_error connector=%s tool=%s error=%s",
                self.connector_name, tool_name, exc,
            )
            return ToolCallResult(
                tool=tool_name,
                connector=self.connector_name,
                success=False,
                error=f"Argument validation failed: {exc}",
                duration_ms=duration_ms,
            )

        # 2. Execution — any handler exception is caught and logged, never
        #    propagated, so one bad external call can't take down the graph.
        try:
            result = registered.handler(**validated.model_dump())
            duration_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "mcp.tool_call.success connector=%s tool=%s duration_ms=%.1f",
                self.connector_name, tool_name, duration_ms,
            )
            return ToolCallResult(
                tool=tool_name,
                connector=self.connector_name,
                success=True,
                result=result,
                duration_ms=duration_ms,
            )
        except Exception as exc:  # noqa: BLE001 — intentional: isolate connector failures
            duration_ms = (time.perf_counter() - started) * 1000
            logger.error(
                "mcp.tool_call.error connector=%s tool=%s error=%s",
                self.connector_name, tool_name, exc,
            )
            return ToolCallResult(
                tool=tool_name,
                connector=self.connector_name,
                success=False,
                error=str(exc),
                duration_ms=duration_ms,
            )

    def get_schema(self, tool_name: str) -> Optional[type[BaseModel]]:
        registered = self._tools.get(tool_name)
        return registered.args_schema if registered else None
