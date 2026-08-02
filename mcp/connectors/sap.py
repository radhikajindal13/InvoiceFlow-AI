"""
mcp/connectors/sap.py
────────────────────────
SAP connector (mock, per brief: "SAP and CRM should have realistic
mocked implementations"). No real SAP system is reachable from this
project, so fetch_invoice / fetch_payment_status return deterministic,
realistic-shaped mock records derived from the invoice number itself
(via a stable hash) rather than random data — the same invoice_no always
returns the same mock record, which is what makes this testable.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from mcp.connector import BaseConnector

_PAYMENT_STATUSES = ["unpaid", "partially_paid", "overdue", "disputed"]
_CURRENCIES = ["INR", "USD", "EUR"]


def _stable_seed(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


class FetchInvoiceArgs(BaseModel):
    invoice_no: str = Field(description="Invoice number to look up in SAP")


class FetchPaymentStatusArgs(BaseModel):
    invoice_no: str = Field(description="Invoice number to check payment status for")


class SapConnector(BaseConnector):
    connector_name = "sap"

    def __init__(self) -> None:
        super().__init__()
        self.tool(
            name="fetch_invoice",
            description="Fetch an invoice record from SAP (mock — deterministic per invoice_no).",
            args_schema=FetchInvoiceArgs,
        )(self._fetch_invoice)

        self.tool(
            name="fetch_payment_status",
            description="Fetch the current payment status for an invoice from SAP (mock).",
            args_schema=FetchPaymentStatusArgs,
        )(self._fetch_payment_status)

    def _fetch_invoice(self, invoice_no: str) -> dict:
        seed = _stable_seed("invoice", invoice_no)
        amount = round(1000 + (seed % 500000) / 100, 2)
        currency = _CURRENCIES[seed % len(_CURRENCIES)]
        posting_date = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=seed % 180)

        return {
            "invoice_no": invoice_no,
            "sap_document_number": f"SAP-{seed % 9_000_000 + 1_000_000}",
            "amount": amount,
            "currency": currency,
            "posting_date": posting_date.date().isoformat(),
            "cost_center": f"CC-{seed % 900 + 100}",
            "source": "sap_mock",
        }

    def _fetch_payment_status(self, invoice_no: str) -> dict:
        seed = _stable_seed("payment_status", invoice_no)
        status = _PAYMENT_STATUSES[seed % len(_PAYMENT_STATUSES)]
        amount_paid = 0.0 if status in ("unpaid", "overdue", "disputed") else round((seed % 5000) / 100, 2)

        return {
            "invoice_no": invoice_no,
            "payment_status": status,
            "amount_paid": amount_paid,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "source": "sap_mock",
        }
