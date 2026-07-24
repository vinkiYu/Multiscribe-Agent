"""Tests for asynchronous DAG workflow execution."""

import asyncio
from collections.abc import Callable

import pytest

from multiscribe_agent.agents.workflow.engine import WorkflowEngine
from multiscribe_agent.agents.workflow.protocols import AgentStepExecutor
from multiscribe_agent.core.errors import AgentStepTerminalError, WorkflowError
from multiscribe_agent.domain.models import WorkflowDefinition, WorkflowStep


class MemoryWorkflowStore:
    """In-memory workflow documents for engine tests."""

    def __init__(self, *workflows: WorkflowDefinition) -> None:
        self._workflows = {workflow.id: workflow.model_dump(mode="json") for workflow in workflows}

    async def get(self, table: str, entity_id: str) -> dict[str, object] | None:
        """Return a workflow record from the expected table."""
        assert table == "workflows"
        return self._workflows.get(entity_id)


class FakeExecutor:
    """Injectable agent executor with observable inputs and optional handlers."""

    def __init__(self, handlers: dict[str, Callable[[str], str]]) -> None:
        self._handlers = handlers
        self.inputs: list[tuple[str, str]] = []

    async def execute(self, agent_id: str, user_input: str) -> str:
        """Record and process one agent request."""
        self.inputs.append((agent_id, user_input))
        return self._handlers[agent_id](user_input)


class ParallelExecutor(FakeExecutor):
    """Measure concurrent executions at one Kahn level."""

    def __init__(self) -> None:
        super().__init__({"a": lambda value: f"a:{value}", "b": lambda value: f"b:{value}"})
        self.active = 0
        self.maximum_active = 0

    async def execute(self, agent_id: str, user_input: str) -> str:
        """Delay execution long enough for concurrently scheduled tasks to overlap."""
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        try:
            await asyncio.sleep(0.03)
            return await super().execute(agent_id, user_input)
        finally:
            self.active -= 1


class TerminalExecutor(FakeExecutor):
    """Raise one structured Agent terminal state before a downstream step can run."""

    async def execute(self, agent_id: str, user_input: str) -> str:
        self.inputs.append((agent_id, user_input))
        raise AgentStepTerminalError(
            "context_budget_exhausted",
            "context exhausted",
            {"actual": 2_000, "limit": 1_000},
        )


def _workflow(workflow_id: str, *steps: WorkflowStep) -> WorkflowDefinition:
    """Build one compact workflow."""
    return WorkflowDefinition(id=workflow_id, name=workflow_id, description="", steps=list(steps))


def _agent(step_id: str, agent_id: str, **kwargs: object) -> WorkflowStep:
    """Build an agent step."""
    return WorkflowStep(id=step_id, name=step_id, step_type="agent", agent_id=agent_id, **kwargs)


@pytest.mark.asyncio
async def test_linear_execution_passes_previous_output() -> None:
    """One-predecessor steps receive their predecessor output."""
    workflow = _workflow("linear", _agent("a", "a", next_step_id="b"), _agent("b", "b"))
    executor = FakeExecutor({"a": lambda value: f"a:{value}", "b": lambda value: f"b:{value}"})

    result = await WorkflowEngine(executor, MemoryWorkflowStore(workflow)).run("linear", "start")

    assert executor.inputs == [("a", "start"), ("b", "a:start")]
    assert result["final"] == "b:a:start"
    assert isinstance(executor, AgentStepExecutor)


@pytest.mark.asyncio
async def test_parallel_level_runs_concurrently() -> None:
    """Independent roots are scheduled through asyncio.gather."""
    workflow = _workflow("parallel", _agent("a", "a"), _agent("b", "b"))
    executor = ParallelExecutor()

    await WorkflowEngine(executor, MemoryWorkflowStore(workflow)).run("parallel", "start")

    assert executor.maximum_active == 2


@pytest.mark.asyncio
async def test_input_map_nested_workflow_and_disabled_pass_through() -> None:
    """Named input mapping, recursion, and disabled nodes preserve data correctly."""
    child = _workflow("child", _agent("child_step", "child"))
    outer = _workflow(
        "outer",
        _agent("first", "first", next_step_ids=["second", "disabled"]),
        _agent("second", "second", input_map={"payload": "first"}),
        WorkflowStep(
            id="disabled",
            name="disabled",
            step_type="workflow",
            workflow_id="child",
            enabled=False,
            next_step_id="nested",
        ),
        WorkflowStep(id="nested", name="nested", step_type="workflow", workflow_id="child"),
    )
    executor = FakeExecutor(
        {
            "first": lambda value: f"first:{value}",
            "second": lambda value: f"second:{value}",
            "child": lambda value: f"child:{value}",
        }
    )

    result = await WorkflowEngine(executor, MemoryWorkflowStore(outer, child)).run("outer", "start")

    assert ("second", "first:start") in executor.inputs
    assert ("child", "first:start") in executor.inputs
    assert result["step_results"]["disabled"] == "first:start"
    assert result["step_results"]["nested"] == "child:first:start"


@pytest.mark.asyncio
async def test_empty_output_halts_downstream_execution() -> None:
    """An empty non-leaf output becomes a workflow error before its successor runs."""
    workflow = _workflow("empty", _agent("a", "a", next_step_id="b"), _agent("b", "b"))
    executor = FakeExecutor({"a": lambda value: "", "b": lambda value: "unexpected"})

    with pytest.raises(WorkflowError, match="empty output"):
        await WorkflowEngine(executor, MemoryWorkflowStore(workflow)).run("empty", "start")

    assert executor.inputs == [("a", "start")]


@pytest.mark.asyncio
async def test_agent_terminal_state_stops_downstream_and_preserves_details() -> None:
    workflow = _workflow("terminal", _agent("a", "a", next_step_id="b"), _agent("b", "b"))
    executor = TerminalExecutor({"a": lambda value: value, "b": lambda value: value})
    engine = WorkflowEngine(executor, MemoryWorkflowStore(workflow))

    events = [event async for event in engine.stream("terminal", "start")]

    assert executor.inputs == [("a", "start")]
    assert [event.type for event in events] == [
        "workflow_start",
        "step_start",
        "step_error",
        "workflow_error",
    ]
    assert events[-1].data["terminal_type"] == "context_budget_exhausted"
    assert events[-1].data["terminal_data"] == {"actual": 2_000, "limit": 1_000}

    with pytest.raises(WorkflowError) as captured:
        await engine.run("terminal", "start")
    assert captured.value.details["terminal_type"] == "context_budget_exhausted"


@pytest.mark.asyncio
async def test_cycle_yields_workflow_error_and_stream_lifecycle_is_complete() -> None:
    """Cycles fail cleanly while successful runs expose all event lifecycle entries."""
    cyclic = _workflow(
        "cycle", _agent("a", "a", next_step_id="b"), _agent("b", "b", next_step_id="a")
    )
    executor = FakeExecutor({"a": lambda value: value, "b": lambda value: value})
    engine = WorkflowEngine(executor, MemoryWorkflowStore(cyclic))

    events = [event async for event in engine.stream("cycle", "start")]

    assert [event.type for event in events] == ["workflow_start", "workflow_error"]
    with pytest.raises(WorkflowError, match="cycle"):
        await engine.run("cycle", "start")

    linear = _workflow("events", _agent("a", "a"))
    event_types = [
        event.type
        async for event in WorkflowEngine(executor, MemoryWorkflowStore(linear)).stream(
            "events", "start"
        )
    ]
    assert event_types == ["workflow_start", "step_start", "step_complete", "workflow_complete"]
