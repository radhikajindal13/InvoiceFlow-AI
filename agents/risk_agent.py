"""
agents/risk_agent.py
────────────────────
Risk Agent (brief Step 5 / Step 17: Risk Score, Recovery Prediction).

Given an invoice, this agent decides for itself which tools it needs
(customer history? invoice history?) and then must call
calculate_risk_score with real numbers to get a final score — the score
itself is never taken from the model's own text, only from the
deterministic tool result, so a fluent-sounding hallucinated "risk: 82"
can't slip through if the tool was never actually called.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base import run_tool_agent
from agents.tools import ALL_TOOLS
from core.models import model  # reuse the existing ChatMistralAI instance

SYSTEM_PROMPT = """You are a credit-risk assessment agent for an accounts
receivable follow-up system. Given an overdue invoice, decide which tools
you need (customer history, invoice history) to understand this client's
track record, then you MUST call calculate_risk_score with the real
numbers you gathered to get the actual risk score. Never state a risk
score you did not get from calculate_risk_score. After the tool call,
give a one-paragraph plain-English explanation of the result."""


class RiskAssessment(BaseModel):
    score: float = Field(description="0-100 risk score from calculate_risk_score")
    band: str = Field(description="low | medium | high | critical")
    reasoning: str = Field(description="Plain-English explanation")
    tool_calls_made: int = Field(description="How many tools the agent actually invoked")


def assess_risk(
    invoice_no: str,
    client_name: str,
    amount: float,
    days_overdue: int,
) -> RiskAssessment:
    user_message = (
        f"Invoice {invoice_no} for client '{client_name}', amount {amount}, "
        f"{days_overdue} days overdue. Assess non-payment risk."
    )
    result = run_tool_agent(model, ALL_TOOLS, SYSTEM_PROMPT, user_message)

    score_call = next(
        (c for c in reversed(result.tool_calls_made) if c["name"] == "calculate_risk_score"),
        None,
    )

    if score_call is None:
        # The agent never actually called the scoring tool (e.g. it
        # answered from a single turn without invoking anything). Rather
        # than trust a number it may have hallucinated in prose, fall back
        # to computing the deterministic score directly with what we know.
        from agents.tools import calculate_risk_score

        fallback = calculate_risk_score.invoke(
            {"days_overdue": days_overdue, "amount": amount}
        )
        return RiskAssessment(
            score=fallback["score"],
            band=fallback["band"],
            reasoning="Risk agent did not invoke calculate_risk_score; "
                      "computed a fallback score directly from overdue "
                      "days and amount only (no customer/invoice history).",
            tool_calls_made=len(result.tool_calls_made),
        )

    score_result = score_call["result"]
    return RiskAssessment(
        score=score_result["score"],
        band=score_result["band"],
        reasoning=result.text or "; ".join(score_result.get("reasons", [])),
        tool_calls_made=len(result.tool_calls_made),
    )
