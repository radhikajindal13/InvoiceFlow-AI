"""
api/routers/mcp_router.py
───────────────────────────
Exposes the MCP layer's two operations — discovery and execution — over
HTTP, on top of the same mcp.client.default_client the coordinator uses
internally. Lets a human or another service inspect what tools exist and
call one directly, without going through the invoice pipeline.
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from mcp.client import default_client

router = APIRouter(prefix="/mcp", tags=["mcp"])


class ToolSpecOut(BaseModel):
    qualified_name: str
    connector: str
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCallRequest(BaseModel):
    tool: str  # qualified name, e.g. "sap.fetch_invoice"
    arguments: dict[str, Any] = {}


class ToolCallResponse(BaseModel):
    tool: str
    connector: str
    success: bool
    result: Any = None
    error: str | None = None
    duration_ms: float


@router.get("/tools", response_model=list[ToolSpecOut])
def list_tools() -> list[ToolSpecOut]:
    """Tool discovery: every tool across every registered connector."""
    return [
        ToolSpecOut(
            qualified_name=spec.qualified_name,
            connector=spec.connector,
            name=spec.name,
            description=spec.description,
            input_schema=spec.input_schema,
        )
        for spec in default_client.list_tools()
    ]


@router.post("/call", response_model=ToolCallResponse)
def call_tool(request: ToolCallRequest) -> ToolCallResponse:
    """Tool execution layer: call any discovered tool by its qualified
    name. Validation, logging, and error handling all happen inside the
    connector (mcp/connector.py::BaseConnector.call_tool) — this endpoint
    never has to know a tool's argument shape ahead of time."""
    result = default_client.call_tool(request.tool, request.arguments)
    return ToolCallResponse(**result.to_dict())
