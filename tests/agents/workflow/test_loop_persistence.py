"""Regression tests for durable Loop checkpoints and resume behavior."""

from __future__ import annotations

import pytest

from multiscribe_agent.agents.workflow.iteration_store import IterationStore
from multiscribe_agent.agents.workflow.loop_node import execute_loop_step
from multiscribe_agent.domain.models import WorkflowStep
from multiscribe_agent.infra.db import init_db


class SequenceExecutor:
    """Return deterministic outputs for each loop round."""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = iter(outputs)

    async def execute(self, agent_id: str, user_input: str) -> str:
        del agent_id, user_input
        return next(self._outputs)


def _loop(max_iterations: int = 3) -> WorkflowStep:
    return WorkflowStep(
        id="loop",
        name="Loop",
        step_type="agent",
        agent_id="writer",
        max_iterations=max_iterations,
    )


@pytest.mark.asyncio
async def test_loop_iterations_persist_and_resume_from_latest_round() -> None:
    """A second process can continue after the first round checkpoint."""
    db = await init_db(":memory:")
    try:
        store = IterationStore(db)
        first_output, first_history = await execute_loop_step(
            _loop(max_iterations=1),
            "task",
            SequenceExecutor(["first"]),
            None,
            trace_id="trace",
            workflow_run_id="run-1",
            iteration_store=store,
        )
        assert first_output == "first"
        assert len(first_history) == 1

        resumed_output, resumed_history = await execute_loop_step(
            _loop(),
            "task",
            SequenceExecutor(["second", "third"]),
            None,
            trace_id="trace",
            workflow_run_id="run-1",
            iteration_store=store,
        )
        assert resumed_output == "third"
        assert len(resumed_history) == 3

        latest = await store.resume_loop("run-1", "loop")
        assert latest is not None
        assert latest.round == 3
        assert latest.output == "third"

        records = await store.list_for_step("run-1", "loop")
        assert [record.round for record in records] == [1, 2, 3]
    finally:
        await db.close()
