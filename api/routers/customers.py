from fastapi import APIRouter

from agents.tools import lookup_customer_history
from api.schemas import CustomerHistoryOut

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/{client_name}/history", response_model=CustomerHistoryOut)
def get_customer_history(client_name: str) -> CustomerHistoryOut:
    """
    Exposes the exact same persistent customer memory the risk agent reads
    before generating a follow-up email (agents/tools.py::lookup_customer_history),
    so a finance user can see why the risk/verifier agents made the call
    they did for a given client.
    """
    result = lookup_customer_history.invoke({"client_name": client_name})
    return CustomerHistoryOut(**result)
