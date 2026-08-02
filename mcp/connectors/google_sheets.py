"""
mcp/connectors/google_sheets.py
─────────────────────────────────
Google Sheets connector: append_google_sheet() as an MCP tool.

No Google service-account credentials are configured for this project, so
this defaults to the dry-run-log pattern (mcp/dry_run_log.py). Real usage
would swap `_append_row`'s body for a `google-api-python-client` call
using `GOOGLE_SHEETS_CREDENTIALS_JSON` + `GOOGLE_SHEETS_SPREADSHEET_ID`
env vars — the tool's schema/signature would not need to change, only
this one method's body, which is the point of the connector interface.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from mcp.connector import BaseConnector
from mcp.dry_run_log import write_dry_run_log


class AppendGoogleSheetArgs(BaseModel):
    spreadsheet_id: str = Field(description="Target Google Sheet ID")
    sheet_name: str = Field(default="Sheet1", description="Worksheet/tab name")
    row_values: list[str] = Field(description="Ordered cell values for the appended row")


class GoogleSheetsConnector(BaseConnector):
    connector_name = "google_sheets"

    def __init__(self) -> None:
        super().__init__()
        self.tool(
            name="append_google_sheet",
            description=(
                "Append a row to a Google Sheet. Dry-run by default "
                "(logged, not sent); set GOOGLE_SHEETS_CREDENTIALS_JSON "
                "to enable a real append."
            ),
            args_schema=AppendGoogleSheetArgs,
        )(self._append_row)

    def _append_row(self, spreadsheet_id: str, row_values: list[str], sheet_name: str = "Sheet1") -> dict:
        if not os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON", "").strip():
            log_path = write_dry_run_log(
                connector="google_sheets",
                tool="append_google_sheet",
                payload={
                    "spreadsheet_id": spreadsheet_id,
                    "sheet_name": sheet_name,
                    "row_values": row_values,
                },
            )
            print(f"[DRY-RUN] Google Sheets append logged → {log_path}")
            return {
                "success": True,
                "dry_run": True,
                "spreadsheet_id": spreadsheet_id,
                "logged_to": log_path,
            }

        raise NotImplementedError(
            "GOOGLE_SHEETS_CREDENTIALS_JSON is set but the real Sheets API "
            "call is not wired up in this environment. Implement here using "
            "google-api-python-client — the tool schema above does not "
            "need to change."
        )
