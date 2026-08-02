"""
mcp/connectors/slack.py
────────────────────────
Slack connector: send_slack_message() as an MCP tool.

No Slack workspace is configured for this project, so this defaults to
the same dry-run-log pattern as core/email_service.py (see
mcp/dry_run_log.py) — safe, deterministic, testable. If SLACK_WEBHOOK_URL
is set, it posts for real via a plain HTTP webhook (Slack's simplest
integration path — no SDK needed). The dry-run/live switch mirrors
EMAIL_PROVIDER exactly on purpose.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from mcp.connector import BaseConnector
from mcp.dry_run_log import write_dry_run_log


class SendSlackMessageArgs(BaseModel):
    channel: str = Field(description="Slack channel, e.g. '#finance-alerts'")
    message: str = Field(description="Message text to post")


class SlackConnector(BaseConnector):
    connector_name = "slack"

    def __init__(self) -> None:
        super().__init__()
        self.tool(
            name="send_slack_message",
            description=(
                "Post a message to a Slack channel. Dry-run by default "
                "(logged, not sent); set SLACK_WEBHOOK_URL to post for real."
            ),
            args_schema=SendSlackMessageArgs,
        )(self._send_slack_message)

    def _send_slack_message(self, channel: str, message: str) -> dict:
        webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()

        if not webhook_url:
            log_path = write_dry_run_log(
                connector="slack",
                tool="send_slack_message",
                payload={"channel": channel, "message": message},
            )
            print(f"[DRY-RUN] Slack message logged → {log_path}")
            return {"success": True, "dry_run": True, "channel": channel, "logged_to": log_path}

        import requests  # imported lazily: only needed on the live path

        response = requests.post(webhook_url, json={"channel": channel, "text": message}, timeout=10)
        response.raise_for_status()
        return {"success": True, "dry_run": False, "channel": channel, "status_code": response.status_code}
