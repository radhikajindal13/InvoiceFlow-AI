"""
mcp/connectors/jira.py
────────────────────────
Jira connector (mock): create_jira_ticket() as an MCP tool.

No Jira instance is configured for this project. Rather than a bare
dry-run log, this simulates the one part of Jira's behavior that matters
to callers — an assigned ticket key — deterministically, so tests can
assert on it: a per-process counter seeded from the dry-run log's current
line count, formatted as project-prefixed keys (FIN-1, FIN-2, ...), the
same shape a real Jira Cloud instance returns.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from mcp.connector import BaseConnector
from mcp.dry_run_log import MCP_DRY_RUN_LOG_PATH, write_dry_run_log


class CreateJiraTicketArgs(BaseModel):
    summary: str = Field(description="Short ticket title")
    description: str = Field(description="Full ticket description/body")
    priority: str = Field(default="Medium", description="Low | Medium | High | Critical")
    project_key: str = Field(default="FIN", description="Jira project key prefix")


def _next_ticket_number(project_key: str) -> int:
    """Deterministic, file-backed counter: count how many tickets for this
    project already exist in the dry-run log, so ticket keys are stable
    and reproducible across a test run instead of random."""
    if not MCP_DRY_RUN_LOG_PATH.exists():
        return 1
    count = 0
    with MCP_DRY_RUN_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if f'"tool": "create_jira_ticket"' in line and f'"{project_key}-' in line:
                count += 1
    return count + 1


class JiraConnector(BaseConnector):
    connector_name = "jira"

    def __init__(self) -> None:
        super().__init__()
        self.tool(
            name="create_jira_ticket",
            description=(
                "Create a Jira ticket for manual finance/legal follow-up. "
                "Mock implementation — assigns a realistic, deterministic "
                "ticket key and logs the ticket, no live Jira instance required."
            ),
            args_schema=CreateJiraTicketArgs,
        )(self._create_ticket)

    def _create_ticket(
        self,
        summary: str,
        description: str,
        priority: str = "Medium",
        project_key: str = "FIN",
    ) -> dict:
        ticket_number = _next_ticket_number(project_key)
        ticket_key = f"{project_key}-{ticket_number}"

        log_path = write_dry_run_log(
            connector="jira",
            tool="create_jira_ticket",
            payload={
                "ticket_key": ticket_key,
                "summary": summary,
                "description": description,
                "priority": priority,
                "status": "Open",
            },
        )
        print(f"[MOCK] Jira ticket {ticket_key} created → {log_path}")

        return {
            "ticket_key": ticket_key,
            "status": "Open",
            "priority": priority,
            "url": f"https://mock-jira.local/browse/{ticket_key}",
        }
