"""Closed-loop context-window behavior at the Agent executor boundary."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from multiscribe_agent.agents.context import ContextPriority, HarnessContext
from multiscribe_agent.agents.executor import AgentExecutor
from multiscribe_agent.agents.prompt_service import PromptService
from multiscribe_agent.core.errors import ProviderContextLengthError
from multiscribe_agent.domain.models import AIMessage, AIResponse, ToolDefinition


class WindowProvider:
    """Provider fake that can reject selected streaming attempts."""

    context_window_tokens = 20_000
    default_output_tokens = 1_000

    def __init__(self, attempts: list[list[AIResponse] | Exception]) -> None:
        self.attempts = list(attempts)
        self.calls = 0
        self.output_limits: list[int | None] = []

    async def stream(
        self,
        messages: list[AIMessage],
        tools: list[ToolDefinition] | None = None,
        system_instruction: str | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[AIResponse]:
        del messages, tools, system_instruction
        self.calls += 1
        self.output_limits.append(max_output_tokens)
        attempt = self.attempts.pop(0)
        if isinstance(attempt, Exception):
            raise attempt
        for response in attempt:
            yield response


async def _events(iterator: AsyncIterator[object]) -> list[object]:
    return [event async for event in iterator]


@pytest.mark.asyncio
async def test_provider_context_rejection_compacts_and_retries_once(agent_def) -> None:
    provider = WindowProvider(
        [ProviderContextLengthError("context_length_exceeded"), [AIResponse(content="ok")]]
    )
    executor = AgentExecutor(lambda _: provider, None, PromptService())

    events = await _events(executor.stream(agent_def, "short request"))

    assert provider.calls == 2
    assert provider.output_limits == [1_000, 1_000]
    compacted = [event for event in events if event.type == "context_compacted"]
    assert compacted[-1].data["retry_count"] == 1
    assert any(event.type == "final_content" for event in events)


@pytest.mark.asyncio
async def test_provider_rejection_after_partial_content_is_not_retried(agent_def) -> None:
    class PartialProvider(WindowProvider):
        async def stream(self, *args: object, **kwargs: object) -> AsyncIterator[AIResponse]:
            del args, kwargs
            self.calls += 1
            yield AIResponse(content="partial")
            raise ProviderContextLengthError("context_length_exceeded")

    provider = PartialProvider([])
    executor = AgentExecutor(lambda _: provider, None, PromptService())

    events = await _events(executor.stream(agent_def, "short request"))

    assert provider.calls == 1
    assert any(event.type == "content" for event in events)
    assert any(event.type == "error" for event in events)


@pytest.mark.asyncio
async def test_second_provider_rejection_returns_context_budget_terminal(agent_def) -> None:
    provider = WindowProvider(
        [
            ProviderContextLengthError("context_length_exceeded"),
            ProviderContextLengthError("context_length_exceeded"),
        ]
    )
    executor = AgentExecutor(lambda _: provider, None, PromptService())

    events = await _events(executor.stream(agent_def, "short request"))

    assert provider.calls == 2
    terminal = [event for event in events if event.type == "context_budget_exhausted"]
    assert terminal[-1].data["retry_count"] == 1
    assert terminal[-1].data["partitions"]["tool_schema"] == 0


@pytest.mark.asyncio
async def test_unresolvable_minimum_context_never_calls_provider(agent_def) -> None:
    provider = WindowProvider([])
    provider.context_window_tokens = 4_000
    provider.default_output_tokens = 3_500
    executor = AgentExecutor(lambda _: provider, None, PromptService())

    response = await executor.run(agent_def, "goal")

    assert provider.calls == 0
    assert "Context budget exhausted" in response.content


@pytest.mark.asyncio
async def test_tool_schema_is_reserved_before_provider_call(agent_def) -> None:
    provider = WindowProvider([])
    provider.context_window_tokens = 2_000
    provider.default_output_tokens = 100
    tool = ToolDefinition(
        id="large",
        name="large_schema",
        description="字段" * 5_000,
        parameters={"type": "object", "properties": {}},
    )

    async def unused_tool(_call: object) -> object:
        raise AssertionError("tool must not execute")

    executor = AgentExecutor(lambda _: provider, None, PromptService())
    events = await _events(executor.stream(agent_def, "goal", tools_override=([tool], unused_tool)))

    assert provider.calls == 0
    terminal = [event for event in events if event.type == "context_budget_exhausted"][-1]
    assert terminal.data["partitions"]["tool_schema"] > 0


def test_optional_context_degrades_before_required_goal() -> None:
    context = HarnessContext("system", token_budget=500)
    context.inject_memory("m" * 2_000)
    context.inject_knowledge(["k" * 2_000])
    context.add_user("required-current-goal", priority=ContextPriority.REQUIRED)

    messages = context.build_messages()

    stages = context.compaction_stages
    assert stages.index("knowledge_removed") < stages.index("memory_removed")
    assert any(message.content == "required-current-goal" for message in messages)
