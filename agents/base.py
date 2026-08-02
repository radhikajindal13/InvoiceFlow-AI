"""
agents/base.py
──────────────
A small, generic tool-calling loop shared by every agent in this package.
This is the actual mechanism that makes "the LLM decides when to call
tools" (brief Step 4) true instead of aspirational: the model is bound to
a real tool list via .bind_tools(), and we keep feeding its tool calls back
to it as ToolMessages until it stops asking for tools or we hit max_steps.

Deliberately framework-light: LangGraph is used where it earns its keep
(the per-invoice worker StateGraph). A ReAct loop like this one doesn't
need its own graph — it's ~20 lines of plain LangChain, and adding a
second graph abstraction here would be complexity for its own sake.
"""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool


class ToolAgentResult:
    def __init__(self, final_message: BaseMessage, tool_calls_made: list[dict], messages: list[BaseMessage]):
        self.final_message = final_message
        self.tool_calls_made = tool_calls_made
        self.messages = messages

    @property
    def text(self) -> str:
        content = self.final_message.content
        return content if isinstance(content, str) else str(content)


def run_tool_agent(
    llm: BaseChatModel,
    tools: list[BaseTool],
    system_prompt: str,
    user_message: str,
    max_steps: int = 4,
) -> ToolAgentResult:
    """
    Standard bind_tools ReAct loop:
        1. Ask the model for a response, with tools available.
        2. If it asked to call tools, execute each one for real and feed
           the result back as a ToolMessage.
        3. Repeat until the model answers without requesting a tool call,
           or max_steps is hit (defensive cap against infinite tool loops).
    """
    tools_by_name: dict[str, Callable[..., Any]] = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)

    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    tool_calls_made: list[dict] = []

    response = llm_with_tools.invoke(messages)
    messages.append(response)

    steps = 0
    while getattr(response, "tool_calls", None) and steps < max_steps:
        for call in response.tool_calls:
            tool_fn = tools_by_name.get(call["name"])
            if tool_fn is None:
                result = {"error": f"Unknown tool: {call['name']}"}
            else:
                result = tool_fn.invoke(call["args"])
            tool_calls_made.append({"name": call["name"], "args": call["args"], "result": result})
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

        response = llm_with_tools.invoke(messages)
        messages.append(response)
        steps += 1

    return ToolAgentResult(final_message=response, tool_calls_made=tool_calls_made, messages=messages)
