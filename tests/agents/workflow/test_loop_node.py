"""P40 usage propagation tests for workflow loop iterations."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from multiscribe_agent.agents.workflow.loop_node import execute_loop_step
from multiscribe_agent.domain.models import TokenUsage, WorkflowStep


class SequenceExecutor:
    """Return one output per bounded loop round."""

    def __init__(self) -> None:
        self._outputs = iter(["draft", "final"])

    async def execute(self, agent_id: str, user_input: str) -> str:
        """Return the next output while satisfying the executor protocol."""
        del agent_id, user_input
        return next(self._outputs)


@dataclass(frozen=True)
class Assessment:
    """Reflection result carrying provider usage."""

    should_retry: bool
    feedback: str
    score: float
    usage: TokenUsage


class UsageReflector:
    """Request one retry and expose usage on each assessment."""

    def __init__(self) -> None:
        self._calls = 0

    async def assess(self, task: str, output: str) -> Assessment:
        """Return a failing first score followed by a passing score."""
        del task, output
        self._calls += 1
        return Assessment(
            should_retry=self._calls == 1,
            feedback="add detail",
            score=7.0 if self._calls == 1 else 9.0,
            usage=TokenUsage(input_tokens=11, output_tokens=3, total_tokens=14),
        )


def _loop_step() -> WorkflowStep:
    """Build a two-round LLM-evaluated workflow step."""
    return WorkflowStep(
        id="loop",
        name="Loop",
        step_type="agent",
        agent_id="writer",
        max_iterations=2,
        exit_condition="llm",
    )


@pytest.mark.asyncio
async def test_loop_history_serializes_reflector_usage() -> None:
    """Each loop iteration carries its reflector token usage in event payloads."""
    output, history = await execute_loop_step(
        _loop_step(),
        "write a concise answer",
        SequenceExecutor(),  # type: ignore[arg-type]
        UsageReflector(),  # type: ignore[arg-type]
        trace_id="trace",
    )

    assert output == "final"
    assert [entry["usage"] for entry in history] == [
        {"input_tokens": 11, "output_tokens": 3, "total_tokens": 14},
        {"input_tokens": 11, "output_tokens": 3, "total_tokens": 14},
    ]
