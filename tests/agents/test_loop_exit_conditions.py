import pytest

from multiscribe_agent.agents.workflow.loop_node import execute_loop_step
from multiscribe_agent.core.errors import WorkflowError
from multiscribe_agent.domain.models import WorkflowStep
from tests.agents.test_loop_node_multi_round import ScoreReflector, SequenceExecutor


def _loop(**kwargs: object) -> WorkflowStep:
    return WorkflowStep(
        id="loop",
        name="Loop",
        step_type="agent",
        agent_id="writer",
        **kwargs,
    )


@pytest.mark.asyncio
async def test_score_delta_exits_when_progress_stalls() -> None:
    output, history = await execute_loop_step(
        _loop(exit_condition="llm", config={"convergence_delta": 0.5}),
        "task",
        SequenceExecutor(["draft", "slightly better"]),
        ScoreReflector([6.0, 6.2]),
        trace_id="trace",
    )
    assert output == "slightly better"
    assert history[-1]["reason"] == "convergence"
    assert history[-1]["converged"] is True


@pytest.mark.asyncio
async def test_max_rounds_exits_without_marking_converged() -> None:
    output, history = await execute_loop_step(
        _loop(exit_condition="llm", config={"max_rounds": 2, "score_threshold": 9.0}),
        "task",
        SequenceExecutor(["one", "two"]),
        ScoreReflector([3.0, 4.0]),
        trace_id="trace",
    )
    assert output == "two"
    assert history[-1]["reason"] == "max_rounds"
    assert history[-1]["converged"] is False


@pytest.mark.asyncio
async def test_rule_condition_exits_without_reflector() -> None:
    output, history = await execute_loop_step(
        _loop(exit_condition="output contains 'DONE'"),
        "task",
        SequenceExecutor(["working", "DONE"]),
        None,
        trace_id="trace",
    )
    assert output == "DONE"
    assert history[-1]["reason"] == "condition"


@pytest.mark.asyncio
async def test_invalid_loop_config_raises() -> None:
    with pytest.raises(WorkflowError, match="max_rounds"):
        await execute_loop_step(
            _loop(exit_condition="llm", config={"max_rounds": 0}),
            "task",
            SequenceExecutor(["one"]),
            ScoreReflector([1.0]),
            trace_id="trace",
        )


@pytest.mark.asyncio
async def test_unsupported_exit_condition_raises() -> None:
    with pytest.raises(WorkflowError, match="unsupported"):
        await execute_loop_step(
            _loop(exit_condition="never"),
            "task",
            SequenceExecutor(["one"]),
            None,
            trace_id="trace",
        )
