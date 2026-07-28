"""P40 tests for preserving structured usage at the bootstrap adapter boundary."""

from __future__ import annotations

import pytest

from multiscribe_agent.agents.reflector import Reflection
from multiscribe_agent.bootstrap import _ProviderLoopReflector, _StoredAgentStepExecutor
from multiscribe_agent.core.errors import AgentStepTerminalError
from multiscribe_agent.domain.models import AgentDefinition, AgentRunResult, TokenUsage


class AgentStore:
    """Return one stored definition through the entity repository boundary."""

    def __init__(self, definition: AgentDefinition) -> None:
        self._definition = definition

    async def get(self, table: str, entity_id: str) -> dict[str, object] | None:
        """Return the requested agent document."""
        assert table == "agents"
        assert entity_id == self._definition.id
        return self._definition.model_dump(mode="json")


class ResultHarness:
    """Return a successful structured result with deterministic usage."""

    async def run_result(self, *_args: object, **_kwargs: object) -> AgentRunResult:
        """Return content and provider usage."""
        return AgentRunResult(
            status="success",
            content="answer",
            usage=TokenUsage(input_tokens=20, output_tokens=4, total_tokens=24),
        )


class TerminalHarness:
    """Return a terminal result so observed execution preserves error semantics."""

    async def run_result(self, *_args: object, **_kwargs: object) -> AgentRunResult:
        """Return a context-budget terminal result."""
        return AgentRunResult(
            status="context_budget_exhausted",
            content="context exhausted",
            terminal_data={"actual": 2_000, "limit": 1_000},
        )


class ReflectionStub:
    """Return a provider reflection with usage for the bootstrap adapter test."""

    async def assess(self, task: str, output: str, provider: object) -> Reflection:
        """Return one successful reflection regardless of provider details."""
        del task, output, provider
        return Reflection(
            quality="pass",
            score=9.0,
            feedback="good",
            should_retry=False,
            usage=TokenUsage(input_tokens=6, output_tokens=2, total_tokens=8),
        )


def _executor(harness: object) -> _StoredAgentStepExecutor:
    """Build the bootstrap adapter around a fake stored agent."""
    definition = AgentDefinition(
        id="agent",
        name="Agent",
        description="test",
        system_prompt="test",
        provider_id="provider",
        model="model",
    )
    return _StoredAgentStepExecutor(
        AgentStore(definition),  # type: ignore[arg-type]
        harness,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_execute_observed_returns_content_and_usage() -> None:
    """Observed execution does not discard the provider token accounting."""
    content, usage = await _executor(ResultHarness()).execute_observed("agent", "input")

    assert content == "answer"
    assert usage == TokenUsage(input_tokens=20, output_tokens=4, total_tokens=24)


@pytest.mark.asyncio
async def test_execute_observed_preserves_terminal_error_contract() -> None:
    """Terminal Agent results still become the workflow terminal exception."""
    with pytest.raises(AgentStepTerminalError) as captured:
        await _executor(TerminalHarness()).execute_observed("agent", "input")

    assert captured.value.terminal_type == "context_budget_exhausted"
    assert captured.value.terminal_data == {"actual": 2_000, "limit": 1_000}


@pytest.mark.asyncio
async def test_provider_loop_reflector_forwards_usage_to_sink() -> None:
    """The reflector adapter keeps usage available to a per-run accumulator."""
    seen: list[TokenUsage] = []
    adapter = _ProviderLoopReflector(ReflectionStub(), object())  # type: ignore[arg-type]
    adapter.set_usage_sink(seen.append)

    assessment = await adapter.assess("task", "answer")

    assert assessment.usage == TokenUsage(input_tokens=6, output_tokens=2, total_tokens=8)
    assert seen == [TokenUsage(input_tokens=6, output_tokens=2, total_tokens=8)]
