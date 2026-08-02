"""
mcp/dry_run_log.py
────────────────────
Shared dry-run logging for connectors that have no real API credentials
configured (Slack, Jira, Google Sheets by default). Deliberately mirrors
core/email_service.py::_send_dry_run — same JSONL-file-append pattern,
same "safe by default, never makes a network call" philosophy — so a
reader who already understands the email dry-run knows exactly what this
does. One shared helper instead of three copies of the same 8 lines.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MCP_DRY_RUN_LOG_PATH = Path(os.getenv("MCP_DRY_RUN_LOG_PATH", "logs/mcp_dry_run.jsonl"))


def write_dry_run_log(connector: str, tool: str, payload: dict[str, Any]) -> str:
    MCP_DRY_RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "connector": connector,
        "tool": tool,
        "mode": "dry_run",
        **payload,
    }

    with MCP_DRY_RUN_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    return str(MCP_DRY_RUN_LOG_PATH)
