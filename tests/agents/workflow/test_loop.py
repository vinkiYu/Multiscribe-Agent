"""Tests for bounded workflow loop execution."""

from dataclasses import dataclass

import pytest

from multiscribe_agent.agents.workflow.loop_node import execute_loop_step
from multiscribe_agent.domain.models import WorkflowStep


class SequenceExecutor:
    """Return configured outputs while retaining inputs for feedback assertions."""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = iter(outputs)
        self.inputs: list[str] = []

    async def execute(self, agent_id: str, user_input: str) -> str:
        """Return the next configured result."""
        del agent_id
        self.inputs.append(user_input)
        return next(self._outputs)


@dataclass(frozen=True)
class Assessment:
    """Minimal reflection value accepted by the loop protocol."""

    should_retry: bool
    feedback: str


class RetryingReflector:
    """Request one retry, then converge."""

    def __init__(self) -> None:
        self.calls = 0

    async def assess(self, task: str, output: str) -> Assessment:
        """Return feedback on the first assessment only."""
        del task, output
        self.calls += 1
        return Assessment(should_retry=self.calls == 1, feedback="add missing detail")


def _loop(**kwargs: object) -> WorkflowStep:
    """Build an agent loop step."""
    max_iterations = int(kwargs.pop("max_iterations", 3))
    return WorkflowStep(
        id="loop",
        name="Loop",
        step_type="agent",
        agent_id="writer",
        max_iterations=max_iterations,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_llm_loop_retries_with_feedback_then_converges() -> None:
    """Reflection feedback is supplied to the retry and records convergence."""
    executor = SequenceExecutor(["draft", "improved"])

    output, history = await execute_loop_step(
        _loop(exit_condition="llm"),
        "original task",
        executor,
        RetryingReflector(),
        trace_id="trace",
    )

    assert output == "improved"
    assert [entry["converged"] for entry in history] == [False, True]
    assert "Feedback from previous attempt:\nadd missing detail" in executor.inputs[1]


@pytest.mark.asyncio
async def test_loop_returns_last_output_at_iteration_limit() -> None:
    """Reaching the hard bound is normal but marks the final history entry unconverged."""
    executor = SequenceExecutor(["one", "two"])

    output, history = await execute_loop_step(
        _loop(max_iterations=2), "task", executor, None, trace_id="trace"
    )

    assert output == "two"
    assert len(history) == 2
    assert history[-1]["converged"] is False


@pytest.mark.asyncio
async def test_rule_exit_condition_stops_when_keyword_appears() -> None:
    """Rule conditions do not require an injected reflector."""
    executor = SequenceExecutor(["working", "status DONE"])

    output, history = await execute_loop_step(
        _loop(exit_condition="output contains 'DONE'"), "task", executor, None, trace_id="trace"
    )

    assert output == "status DONE"
    assert len(history) == 2
    assert history[-1]["converged"] is True
