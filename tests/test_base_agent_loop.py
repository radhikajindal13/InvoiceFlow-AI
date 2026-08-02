"""
Tests the actual tool-calling orchestration in agents/base.py using a fake
chat model, so the loop logic (bind_tools, feeding ToolMessages back,
stopping condition, max_steps cap) is verified without needing network
access to a real LLM provider.
"""
import uuid

from langchain_core.messages import AIMessage

from agents.base import run_tool_agent
from agents.tools import calculate_risk_score


class ScriptedFakeModel:
    """Minimal fake chat model: bind_tools is a no-op (tools are ignored by
    the fake, since we're only testing our own loop, not real tool-choice
    behavior), and .invoke() returns messages from a fixed script in order."""

    def __init__(self, script: list[AIMessage]):
        self._script = list(script)
        self._i = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        msg = self._script[self._i]
        self._i = min(self._i + 1, len(self._script) - 1)
        return msg


def test_run_tool_agent_calls_tool_then_stops():
    call_id = str(uuid.uuid4())
    script = [
        AIMessage(
            content="",
            tool_calls=[{
                "name": "calculate_risk_score",
                "args": {"days_overdue": 60, "amount": 300000},
                "id": call_id,
            }],
        ),
        AIMessage(content="Risk is high given the 60 days overdue."),
    ]
    fake = ScriptedFakeModel(script)

    result = run_tool_agent(
        llm=fake,
        tools=[calculate_risk_score],
        system_prompt="test",
        user_message="assess this invoice",
    )

    assert len(result.tool_calls_made) == 1
    assert result.tool_calls_made[0]["name"] == "calculate_risk_score"
    assert result.tool_calls_made[0]["result"]["band"] in ("high", "critical")
    assert "high" in result.text.lower() or "overdue" in result.text.lower()


def test_run_tool_agent_stops_without_any_tool_call():
    fake = ScriptedFakeModel([AIMessage(content="No tools needed, low risk.")])

    result = run_tool_agent(
        llm=fake,
        tools=[calculate_risk_score],
        system_prompt="test",
        user_message="assess this invoice",
    )

    assert result.tool_calls_made == []
    assert "low risk" in result.text.lower()


def test_run_tool_agent_respects_max_steps():
    call_id = str(uuid.uuid4())
    always_calls_tool = AIMessage(
        content="",
        tool_calls=[{
            "name": "calculate_risk_score",
            "args": {"days_overdue": 1, "amount": 100},
            "id": call_id,
        }],
    )

    class LoopingFakeModel:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            return always_calls_tool

    result = run_tool_agent(
        llm=LoopingFakeModel(),
        tools=[calculate_risk_score],
        system_prompt="test",
        user_message="x",
        max_steps=3,
    )

    # Bounded by max_steps even though the fake model never stops asking
    # for tool calls — this is the defensive cap doing its job.
    assert len(result.tool_calls_made) == 3
