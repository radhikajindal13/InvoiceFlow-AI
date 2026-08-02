"""
mcp/connectors/outlook.py
────────────────────────
Outlook connector: exposes send_email() as an MCP tool.

This is the one connector that is NOT a mock — it delegates straight to
the existing, already-working core/email_service.py::send_email, which
already supports dry_run/sendgrid via EMAIL_PROVIDER. Wrapping a real
service behind the MCP interface (rather than re-implementing "Outlook"
from scratch) is the point: MCP is an interface layer, not a place to
duplicate business logic that already exists and already works.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.email_service import send_email
from mcp.connector import BaseConnector


class SendEmailArgs(BaseModel):
    to: str = Field(description="Recipient email address")
    subject: str = Field(description="Email subject line")
    body: str = Field(description="Plain-text email body")
    invoice_no: str = Field(default="", description="Related invoice number, for logging")
    tone: str = Field(default="", description="Tone used, for logging")


class OutlookConnector(BaseConnector):
    connector_name = "outlook"

    def __init__(self) -> None:
        super().__init__()
        self.tool(
            name="send_email",
            description=(
                "Send an email via Outlook. Respects the EMAIL_PROVIDER "
                "env var (dry_run by default) — same provider switch as "
                "the rest of the app, so this never sends for real unless "
                "explicitly configured to."
            ),
            args_schema=SendEmailArgs,
        )(self._send_email)

    def _send_email(
        self,
        to: str,
        subject: str,
        body: str,
        invoice_no: str = "",
        tone: str = "",
    ) -> dict:
        result = send_email(to=to, subject=subject, body=body, invoice_no=invoice_no, tone=tone)
        return {
            "success": result.success,
            "provider": result.provider,
            "message": result.message,
            "dry_run": result.dry_run,
        }
