"""Tests for AgentExecutor ReAct rounds and emitted event sequences."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from conftest import FakeProvider, FakeTool

from multiscribe_agent.agents.events import AgentEvent
from multiscribe_agent.agents.executor import MAX_SKILL_PROMPT_CHARS, AgentExecutor
from multiscribe_agent.agents.prompt_service import PromptService
from multiscribe_agent.agents.reflector import Reflection, Reflector
from multiscribe_agent.domain.models import (
    AgentDefinition,
    AIResponse,
    SkillEntry,
    SkillFrontmatter,
    TokenUsage,
    ToolCall,
)
from multiscribe_agent.llm.provider import AIProvider
from multiscribe_agent.skills.registry import get_skill_registry


async def collect(events: AsyncIterator[AgentEvent]) -> list[AgentEvent]:
    """Materialize an Agent event stream for sequence assertions."""
    return [event async for event in events]


def make_executor(
    provider: FakeProvider,
    *,
    reflector: object | None = None,
    max_rounds: int = 5,
    max_llm_calls: int | None = None,
) -> AgentExecutor:
    """Create an executor around one deterministic provider."""
    return AgentExecutor(
        lambda _: provider,
        None,
        PromptService(),
        reflector=reflector,
        max_rounds=max_rounds,
        max_llm_calls=max_llm_calls,
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

    async def assess(
        self,
        task: str,
        output: str,
        provider: AIProvider,
        *,
        max_output_tokens: int | None = None,
    ) -> Reflection:
        """Return fail once, then pass."""
        del task, output, provider, max_output_tokens
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
async def test_reflection_usage_and_output_limit_are_in_run_budget(
    agent_def: AgentDefinition,
) -> None:
    provider = FakeProvider(
        streamed_rounds=[
            [
                AIResponse(
                    content="draft",
                    usage=TokenUsage(input_tokens=4, output_tokens=2, total_tokens=6),
                )
            ]
        ],
        generated_responses=[
            AIResponse(
                content='{"quality":"pass","score":9,"feedback":"ok"}',
                usage=TokenUsage(input_tokens=7, output_tokens=3, total_tokens=10),
            )
        ],
    )
    executor = make_executor(provider, reflector=Reflector())

    result = await executor.run_result(agent_def, "write answer")

    assert result.status == "success"
    assert result.usage == TokenUsage(input_tokens=11, output_tokens=5, total_tokens=16)
    assert provider.generate_output_limits == [512]


@pytest.mark.asyncio
async def test_reflection_is_skipped_when_llm_call_budget_is_exhausted(
    agent_def: AgentDefinition,
) -> None:
    provider = FakeProvider(
        streamed_rounds=[[AIResponse(content="best available")]],
        generated_responses=[AIResponse(content='{"quality":"pass","score":9,"feedback":"ok"}')],
    )
    executor = make_executor(provider, reflector=Reflector(), max_llm_calls=1)

    result = await executor.run_result(agent_def, "write answer")

    assert result.status == "budget_exhausted"
    assert result.content == "best available"
    assert provider.generate_inputs == []


@pytest.mark.asyncio
async def test_invalid_reflection_response_is_conservatively_charged(
    agent_def: AgentDefinition,
) -> None:
    provider = FakeProvider(
        streamed_rounds=[
            [
                AIResponse(
                    content="best available",
                    usage=TokenUsage(input_tokens=2, output_tokens=1, total_tokens=3),
                )
            ]
        ],
        generated_responses=[AIResponse(content="invalid reflection")],
    )
    executor = make_executor(provider, reflector=Reflector())

    result = await executor.run_result(agent_def, "write answer")

    assert result.status == "error"
    assert result.usage is not None
    assert result.usage.input_tokens > 2
    assert result.usage.output_tokens == 513


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


@pytest.mark.asyncio
async def test_memory_summaries_are_injected_into_system_context(
    agent_def: AgentDefinition,
) -> None:
    """Callers can supply bounded durable memories without changing the user task."""
    provider = FakeProvider([[AIResponse(content="answer")]])

    await make_executor(provider).run(
        agent_def,
        "question",
        memory_summaries=["Prefer Agent and RAG engineering content."],
    )

    assert "[Memory Data]" in provider.stream_inputs[0][0].content
    assert "Prefer Agent and RAG engineering content." in provider.stream_inputs[0][0].content


def test_skill_prompt_total_chars_are_capped(agent_def: AgentDefinition) -> None:
    """Five large skills cannot consume more than the fixed system-prompt allowance."""
    registry = get_skill_registry()
    registry.clear()
    skill_ids = [f"large-skill-{index}" for index in range(5)]
    try:
        for skill_id in skill_ids:
            registry.register(
                SkillEntry(
                    id=skill_id,
                    name=skill_id,
                    description="Large instruction bundle",
                    instructions="x" * 1_500,
                    is_builtin=True,
                    frontmatter=SkillFrontmatter(
                        name=skill_id,
                        description="Large instruction bundle",
                    ),
                )
            )
        configured = agent_def.model_copy(update={"skill_ids": skill_ids})
        executor = make_executor(FakeProvider([[AIResponse(content="unused")]]))

        system_prompt = executor._build_system_prompt(configured)
        skill_prompt = system_prompt.split("## Available Skills\n\n", maxsplit=1)[1].rstrip("\n")

        assert len(skill_prompt) <= MAX_SKILL_PROMPT_CHARS
        assert "...[truncated]" in skill_prompt
    finally:
        registry.clear()
