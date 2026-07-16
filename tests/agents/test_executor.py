"""Tests for AgentExecutor ReAct rounds and emitted event sequences."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from conftest import FakeProvider, FakeTool

from multiscribe_agent.agents.events import AgentEvent
from multiscribe_agent.agents.executor import AgentExecutor
from multiscribe_agent.agents.prompt_service import PromptService
from multiscribe_agent.agents.reflector import Reflection
from multiscribe_agent.domain.models import AgentDefinition, AIResponse, TokenUsage, ToolCall
from multiscribe_agent.llm.provider import AIProvider


async def collect(events: AsyncIterator[AgentEvent]) -> list[AgentEvent]:
    """Materialize an Agent event stream for sequence assertions."""
    return [event async for event in events]


def make_executor(
    provider: FakeProvider,
    *,
    reflector: object | None = None,
    max_rounds: int = 5,
) -> AgentExecutor:
    """Create an executor around one deterministic provider."""
    return AgentExecutor(
        lambda _: provider,
        None,
        PromptService(),
        reflector=reflector,
        max_rounds=max_rounds,
    )


@pytest.mark.asyncio
async def test_one_round_without_tools_emits_final_content(agent_def: AgentDefinition) -> None:
    """A direct answer completes in one round with content, usage, and final events."""
    provider = FakeProvider(
        [
            [
                AIResponse(
                    content="final answer",
                    usage=TokenUsage(input_tokens=3, output_tokens=2, total_tokens=5),
                )
            ]
        ]
    )

    events = await collect(make_executor(provider).stream(agent_def, "question"))

    assert [event.type for event in events] == [
        "round_start",
        "content",
        "usage",
        "final_content",
    ]
    assert events[-1].data["content"] == "final answer"
    assert events[-1].trace_id == events[0].trace_id


@pytest.mark.asyncio
async def test_tool_call_runs_two_rounds_in_expected_sequence(agent_def: AgentDefinition) -> None:
    """Tool call, result, and final model answer form a complete ReAct sequence."""
    tool_call = ToolCall(id="call-1", name="get_weather", arguments={"city": "Beijing"})
    provider = FakeProvider(
        [
            [AIResponse(content="", tool_calls=[tool_call])],
            [AIResponse(content="It is sunny.")],
        ]
    )
    tool = FakeTool()

    events = await collect(
        make_executor(provider).stream(
            agent_def, "weather?", tools_override=([tool.definition], tool)
        )
    )

    assert [event.type for event in events] == [
        "round_start",
        "tool_calls_delta",
        "usage",
        "tool_calls",
        "tool_start",
        "tool_result",
        "round_start",
        "content",
        "usage",
        "final_content",
    ]
    assert provider.stream_inputs[1][-1].role == "tool"
    assert provider.stream_inputs[1][-1].content == '{"forecast": "sunny"}'


@pytest.mark.asyncio
async def test_max_rounds_yields_error_gracefully(agent_def: AgentDefinition) -> None:
    """A continuing tool loop stops with an observable error at the configured limit."""
    tool_call = ToolCall(id="call-limit", name="get_weather", arguments={})
    provider = FakeProvider([[AIResponse(content="", tool_calls=[tool_call])]])
    tool = FakeTool()

    events = await collect(
        make_executor(provider, max_rounds=1).stream(
            agent_def, "loop", tools_override=([tool.definition], tool)
        )
    )

    assert events[-1].type == "error"
    assert events[-1].data["message"] == "maximum rounds reached (1)"


@pytest.mark.asyncio
async def test_tool_exception_emits_error_and_loop_continues(agent_def: AgentDefinition) -> None:
    """A tool failure becomes context and an event instead of crashing the executor."""
    tool_call = ToolCall(id="call-error", name="get_weather", arguments={})
    provider = FakeProvider(
        [
            [AIResponse(content="", tool_calls=[tool_call])],
            [AIResponse(content="Recovered answer")],
        ]
    )
    tool = FakeTool(fail=True)

    events = await collect(
        make_executor(provider).stream(
            agent_def, "weather?", tools_override=([tool.definition], tool)
        )
    )

    assert "tool_error" in [event.type for event in events]
    assert events[-1].type == "final_content"
    assert provider.stream_inputs[1][-1].content.startswith("[tool error]")


class FailingOnceReflector:
    """Reflection test double that requests exactly one retry."""

    def __init__(self) -> None:
        self.calls = 0

    async def assess(self, task: str, output: str, provider: AIProvider) -> Reflection:
        """Return fail once, then pass."""
        del task, output, provider
        self.calls += 1
        return Reflection(
            quality="fail",
            score=0.2,
            feedback="Add concrete evidence.",
            should_retry=True,
        )


@pytest.mark.asyncio
async def test_reflector_failure_triggers_visible_retry(agent_def: AgentDefinition) -> None:
    """Failed reflection injects feedback and causes a second model round."""
    provider = FakeProvider(
        [
            [AIResponse(content="weak draft")],
            [AIResponse(content="improved final")],
        ]
    )
    reflector = FailingOnceReflector()

    events = await collect(
        make_executor(provider, reflector=reflector).stream(agent_def, "write answer")
    )

    assert [event.type for event in events].count("round_start") == 2
    assert events[-1].type == "final_content"
    assert events[-1].data["content"] == "improved final"
    assert "Add concrete evidence." in provider.stream_inputs[1][-1].content


@pytest.mark.asyncio
async def test_run_returns_final_response(agent_def: AgentDefinition) -> None:
    """The non-streaming facade returns the final content and cumulative usage."""
    provider = FakeProvider(
        [
            [
                AIResponse(
                    content="answer",
                    usage=TokenUsage(input_tokens=4, output_tokens=3, total_tokens=7),
                )
            ]
        ]
    )

    response = await make_executor(provider).run(agent_def, "question")

    assert response.content == "answer"
    assert response.usage is not None
    assert response.usage.total_tokens == 7
