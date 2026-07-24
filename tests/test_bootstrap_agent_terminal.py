"""Workflow composition preserves structured Agent terminal states."""

from __future__ import annotations

import pytest

from multiscribe_agent.bootstrap import _StoredAgentStepExecutor
from multiscribe_agent.core.errors import AgentStepTerminalError
from multiscribe_agent.domain.models import AgentDefinition, AgentRunResult


class AgentStore:
    """Return one persisted Agent definition through the repository boundary."""

    def __init__(self, definition: AgentDefinition) -> None:
        self._definition = definition

    async def get(self, table: str, entity_id: str) -> dict[str, object] | None:
        assert table == "agents"
        assert entity_id == self._definition.id
        return self._definition.model_dump(mode="json")


class TerminalHarness:
    """Return the same terminal result produced by AgentExecutor.run_result()."""

    async def run_result(self, *_args: object, **_kwargs: object) -> AgentRunResult:
        return AgentRunResult(
            status="context_budget_exhausted",
            content="context exhausted",
            terminal_data={"actual": 2_000, "limit": 1_000},
        )


@pytest.mark.asyncio
async def test_stored_agent_step_converts_terminal_result_to_workflow_error() -> None:
    definition = AgentDefinition(
        id="agent",
        name="Agent",
        description="test",
        system_prompt="test",
        provider_id="provider",
        model="model",
    )
    executor = _StoredAgentStepExecutor(
        AgentStore(definition),  # type: ignore[arg-type]
        TerminalHarness(),  # type: ignore[arg-type]
    )

    with pytest.raises(AgentStepTerminalError) as captured:
        await executor.execute("agent", "input")

    assert captured.value.terminal_type == "context_budget_exhausted"
    assert captured.value.terminal_data == {"actual": 2_000, "limit": 1_000}
