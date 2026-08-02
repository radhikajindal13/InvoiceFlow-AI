"""
mcp/connectors/crm.py
────────────────────────
CRM connector: fetch_customer() (mock — no real CRM is configured) and
get_customer_history() (real — backed by the same database/memory_repository.py
and database/audit_repository.py the risk/verifier agents already use).

get_customer_history deliberately reuses the real repositories rather than
inventing CRM-shaped mock history: a real CRM integration's "customer
history" tool would, in practice, often pull from your own systems (billing,
support tickets) rather than the CRM's own database — this mirrors that.
fetch_customer mocks the fields no such internal system has (industry,
account tier, assigned rep), deterministically per client name.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, Field

from database.memory_repository import CustomerMemoryRepository
from mcp.connector import BaseConnector

_INDUSTRIES = ["Manufacturing", "Retail", "Technology", "Logistics", "Healthcare", "Construction"]
_TIERS = ["Standard", "Silver", "Gold", "Platinum"]
_REPS = ["Priya Nair", "Rahul Mehta", "Ananya Iyer", "Karan Shah"]


def _stable_seed(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


class FetchCustomerArgs(BaseModel):
    client_name: str = Field(description="Client/company name to look up in the CRM")


class GetCustomerHistoryArgs(BaseModel):
    client_name: str = Field(description="Client/company name to fetch interaction history for")


class CrmConnector(BaseConnector):
    connector_name = "crm"

    def __init__(self) -> None:
        super().__init__()
        self._memory_repo = CustomerMemoryRepository()

        self.tool(
            name="fetch_customer",
            description="Fetch a customer's CRM profile (mock — deterministic per client_name).",
            args_schema=FetchCustomerArgs,
        )(self._fetch_customer)

        self.tool(
            name="get_customer_history",
            description=(
                "Fetch a customer's real interaction history (reminders sent, "
                "escalations, validation rejections) from this system's own "
                "records — not mocked."
            ),
            args_schema=GetCustomerHistoryArgs,
        )(self._get_customer_history)

    def _fetch_customer(self, client_name: str) -> dict:
        seed = _stable_seed("customer", client_name)
        return {
            "client_name": client_name,
            "crm_id": f"CUST-{seed % 90000 + 10000}",
            "industry": _INDUSTRIES[seed % len(_INDUSTRIES)],
            "account_tier": _TIERS[seed % len(_TIERS)],
            "account_manager": _REPS[seed % len(_REPS)],
            "source": "crm_mock",
        }

    def _get_customer_history(self, client_name: str) -> dict:
        summary = self._memory_repo.get_summary(client_name)
        if not summary:
            return {
                "client_name": client_name,
                "is_known_client": False,
                "reminders_sent": 0,
                "escalations": 0,
                "emails_rejected_in_validation": 0,
            }
        return {
            "client_name": client_name,
            "is_known_client": True,
            "reminders_sent": summary["reminders_sent"],
            "escalations": summary["escalations"],
            "emails_rejected_in_validation": summary["emails_rejected_in_validation"],
            "last_tone_used": summary["last_tone_used"],
            "last_interaction_at": summary["last_interaction_at"],
        }
