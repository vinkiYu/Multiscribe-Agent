"""Regression tests for ReAct deadlock detection and budget warnings."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from conftest import FakeProvider, FakeTool

from multiscribe_agent.agents.events import AgentEvent
from multiscribe_agent.agents.executor import AgentExecutor
from multiscribe_agent.agents.prompt_service import PromptService
from multiscribe_agent.domain.models import AIResponse, ToolCall


async def _collect(events: AsyncIterator[AgentEvent]) -> list[AgentEvent]:
    return [event async for event in events]


@pytest.mark.asyncio
async def test_repeated_tool_call_yields_loop_detected_and_stops(agent_def) -> None:
    """Three identical calls stop before the third tool invocation."""
    call = ToolCall(id="repeat", name="get_weather", arguments={"city": "Beijing"})
    provider = FakeProvider([[AIResponse(content="", tool_calls=[call])] for _ in range(3)])
    tool = FakeTool()
    executor = AgentExecutor(lambda _: provider, None, PromptService(), max_rounds=5)

    events = await _collect(
        executor.stream(agent_def, "weather", tools_override=([tool.definition], tool))
    )

    assert events[-1].type == "loop_detected"
    assert events[-1].data["consecutive_repeats"] == 3
    assert len(tool.calls) == 2


@pytest.mark.asyncio
async def test_budget_warning_is_non_blocking(agent_def) -> None:
    """A high budget estimate emits a warning and still returns final content."""
    provider = FakeProvider([[AIResponse(content="final")]])
    executor = AgentExecutor(
        lambda _: provider,
        None,
        PromptService(),
        token_budget=20,
    )

    events = await _collect(executor.stream(agent_def, "a" * 200))

    assert any(event.type == "budget_warning" for event in events)
    assert events[-1].type == "final_content"
