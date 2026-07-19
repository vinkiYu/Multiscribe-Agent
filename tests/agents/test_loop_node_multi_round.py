from dataclasses import dataclass

import pytest

from multiscribe_agent.agents.workflow.loop_node import LoopSpec, execute_loop_step
from multiscribe_agent.domain.models import WorkflowStep


class SequenceExecutor:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = iter(outputs)
        self.inputs: list[str] = []

    async def execute(self, agent_id: str, user_input: str) -> str:
        del agent_id
        self.inputs.append(user_input)
        return next(self._outputs)


@dataclass(frozen=True)
class Assessment:
    should_retry: bool
    feedback: str
    score: float


class ScoreReflector:
    def __init__(self, scores: list[float]) -> None:
        self._scores = iter(scores)

    async def assess(self, task: str, output: str) -> Assessment:
        del task, output
        score = next(self._scores)
        return Assessment(should_retry=score <= 8.0, feedback=f"score={score}", score=score)


def _loop(**kwargs: object) -> WorkflowStep:
    return WorkflowStep(
        id="loop",
        name="Loop",
        step_type="agent",
        agent_id="writer",
        exit_condition="llm",
        **kwargs,
    )


def test_loop_spec_defaults() -> None:
    assert LoopSpec().max_rounds == 3
    assert LoopSpec().score_threshold == 8.0
    assert LoopSpec().convergence_delta == 0.5


@pytest.mark.asyncio
async def test_multi_round_exits_on_third_score_threshold() -> None:
    executor = SequenceExecutor(["draft", "better", "best"])
    output, history = await execute_loop_step(
        _loop(),
        "task",
        executor,
        ScoreReflector([6.0, 7.0, 8.5]),
        trace_id="trace",
    )
    assert output == "best"
    assert [entry["score"] for entry in history] == [6.0, 7.0, 8.5]
    assert history[1]["delta"] == 1.0
    assert history[-1]["reason"] == "threshold"
    assert history[-1]["converged"] is True


@pytest.mark.asyncio
async def test_loop_feedback_is_passed_to_next_round() -> None:
    executor = SequenceExecutor(["draft", "best"])
    await execute_loop_step(
        _loop(config={"score_threshold": 8.0}),
        "task",
        executor,
        ScoreReflector([6.0, 8.5]),
        trace_id="trace",
    )
    assert "Feedback from previous attempt:\nscore=6.0" in executor.inputs[1]
