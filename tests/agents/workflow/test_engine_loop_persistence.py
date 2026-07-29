"""Verify WorkflowEngine production wiring for durable Loop iterations."""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from multiscribe_agent.agents.workflow.engine import WorkflowEngine
from multiscribe_agent.agents.workflow.iteration_store import IterationRecord, IterationStore
from multiscribe_agent.domain.models import WorkflowDefinition, WorkflowStep
from multiscribe_agent.infra.db import init_db


class MemoryWorkflowStore:
    """Return one in-memory workflow document to the engine."""

    def __init__(self, workflow: WorkflowDefinition) -> None:
        self._workflow = workflow.model_dump(mode="json")

    async def get(self, table: str, entity_id: str) -> dict[str, object] | None:
        """Read the expected workflow record."""
        if table == "workflows" and entity_id == str(self._workflow["id"]):
            return self._workflow
        return None


class SequenceExecutor:
    """Produce deterministic outputs while exposing the number of rounds."""

    def __init__(self, outputs: Iterable[str]) -> None:
        self._outputs = iter(outputs)
        self.calls = 0

    async def execute(self, agent_id: str, user_input: str) -> str:
        """Return the next output for the configured agent."""
        assert agent_id == "writer"
        del user_input
        self.calls += 1
        return next(self._outputs)


def _workflow(max_iterations: int) -> WorkflowDefinition:
    """Build a single-node loop workflow."""
    return WorkflowDefinition(
        id="loop-workflow",
        name="Loop workflow",
        description="",
        steps=[
            WorkflowStep(
                id="loop",
                name="Loop",
                step_type="agent",
                agent_id="writer",
                max_iterations=max_iterations,
            )
        ],
    )


def _loop_step(max_iterations: int) -> WorkflowStep:
    """Build the loop step used by the workflow and direct engine checks."""
    return WorkflowStep(
        id="loop",
        name="Loop",
        step_type="agent",
        agent_id="writer",
        max_iterations=max_iterations,
    )


@pytest.mark.asyncio
async def test_engine_persists_loop_rounds_and_same_run_resumes() -> None:
    """The engine forwards its run trace to Loop persistence and resumes it."""
    db = await init_db(":memory:")
    try:
        store = IterationStore(db)
        workflow_store = MemoryWorkflowStore(_workflow(1))
        executor = SequenceExecutor(["first", "second", "third"])
        engine = WorkflowEngine(executor, workflow_store, iteration_store=store)

        first, _ = await engine._execute_step(_loop_step(1), "task", "run-1", 300.0)
        assert first == "first"

        engine = WorkflowEngine(executor, MemoryWorkflowStore(_workflow(3)), iteration_store=store)
        second, history = await engine._execute_step(_loop_step(3), "task", "run-1", 300.0)
        assert second == "third"
        assert [entry["iteration"] for entry in history] == [1, 2, 3]
        records = await store.list_for_step("run-1", "loop")
        assert [record.round for record in records] == [1, 2, 3]
        assert executor.calls == 3
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_engine_without_iteration_store_keeps_existing_behavior() -> None:
    """The optional store remains a no-op for existing engine callers."""
    db = await init_db(":memory:")
    try:
        workflow = _workflow(1)
        engine = WorkflowEngine(SequenceExecutor(["output"]), MemoryWorkflowStore(workflow))
        result = await engine.run("loop-workflow", "task")
        row = await db.fetchone("SELECT COUNT(*) AS count FROM workflow_iterations")
        assert result["final"] == "output"
        assert row is not None
        assert row["count"] == 0
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_iteration_store_list_recent_is_bounded_and_newest_first() -> None:
    """Recent iteration reads span runs and honor the requested limit."""
    db = await init_db(":memory:")
    try:
        store = IterationStore(db)
        for index in range(3):
            await store.append(
                IterationRecord(
                    workflow_run_id=f"run-{index}",
                    step_id="loop",
                    round=index + 1,
                    output=f"output-{index}",
                    score=None,
                    feedback=None,
                    converged=False,
                    reason="max_rounds",
                )
            )
            await db.execute(
                "UPDATE workflow_iterations SET recorded_at = ? WHERE workflow_run_id = ?",
                (index + 1, f"run-{index}"),
            )
        recent = await store.list_recent(limit=2)
        assert len(recent) == 2
        assert [record.workflow_run_id for record in recent] == ["run-2", "run-1"]
    finally:
        await db.close()
