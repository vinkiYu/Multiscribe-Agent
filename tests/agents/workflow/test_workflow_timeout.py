"""Regression tests for WorkflowEngine total execution timeouts."""

import asyncio

import pytest

from multiscribe_agent.agents.workflow.engine import WorkflowEngine
from multiscribe_agent.core.errors import WorkflowError
from multiscribe_agent.domain.models import WorkflowDefinition, WorkflowStep


class MemoryWorkflowStore:
    """In-memory workflow store for timeout-focused tests."""

    def __init__(self, workflow: WorkflowDefinition) -> None:
        self._workflow = workflow.model_dump(mode="json")

    async def get(self, table: str, entity_id: str) -> dict[str, object] | None:
        """Return the only configured workflow."""
        if table == "workflows" and entity_id == self._workflow["id"]:
            return self._workflow
        return None


class SlowExecutor:
    """Agent executor that never completes before the test timeout."""

    async def execute(self, agent_id: str, user_input: str) -> str:
        """Sleep longer than the workflow deadline."""
        del agent_id, user_input
        await asyncio.sleep(1)
        return "unreachable"


def _workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="slow",
        name="Slow workflow",
        description="",
        steps=[
            WorkflowStep(
                id="step",
                name="Slow step",
                step_type="agent",
                agent_id="slow-agent",
            )
        ],
    )


@pytest.mark.asyncio
async def test_stream_yields_workflow_error_after_timeout() -> None:
    """A timed-out step is converted into a workflow_error lifecycle event."""
    engine = WorkflowEngine(SlowExecutor(), MemoryWorkflowStore(_workflow()))

    events = [event async for event in engine.stream("slow", "input", timeout=0.01)]

    assert events[-1].type == "workflow_error"
    assert "Timeout" in str(events[-1].data["message"])
    assert events[-1].data["timeout"] == 0.01


@pytest.mark.asyncio
async def test_run_raises_domain_error_for_timeout_event() -> None:
    """The aggregate run API preserves its existing WorkflowError contract."""
    engine = WorkflowEngine(SlowExecutor(), MemoryWorkflowStore(_workflow()))

    with pytest.raises(WorkflowError, match="Timeout"):
        await engine.run("slow", "input", timeout=0.01)


@pytest.mark.asyncio
async def test_non_positive_timeout_is_rejected() -> None:
    """Invalid deadlines fail before a workflow can be started."""
    engine = WorkflowEngine(SlowExecutor(), MemoryWorkflowStore(_workflow()))

    with pytest.raises(ValueError, match="timeout must be positive"):
        _ = [event async for event in engine.stream("slow", "input", timeout=0)]
