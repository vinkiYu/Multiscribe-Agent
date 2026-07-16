"""Bounded workflow loop execution."""

from __future__ import annotations

import re

from multiscribe_agent.agents.workflow.protocols import AgentStepExecutor, LoopReflector
from multiscribe_agent.core.errors import WorkflowError
from multiscribe_agent.domain.models import WorkflowStep


async def execute_loop_step(
    step: WorkflowStep,
    step_input: str,
    executor: AgentStepExecutor,
    reflector: LoopReflector | None,
    *,
    trace_id: str,
) -> tuple[str, list[dict[str, object]]]:
    """Execute an agent step until its exit condition converges or reaches its bound."""
    del trace_id
    if step.agent_id is None:
        raise WorkflowError("loop step requires agent_id")
    task = step_input
    current_input = step_input
    history: list[dict[str, object]] = []
    for iteration in range(1, (step.max_iterations or 3) + 1):
        output = await executor.execute(step.agent_id, current_input)
        converged, feedback = await _evaluate_exit_condition(
            step.exit_condition, task, output, reflector
        )
        record: dict[str, object] = {
            "iteration": iteration,
            "output": output,
            "converged": converged,
        }
        if feedback is not None:
            record["feedback"] = feedback
        history.append(record)
        if converged:
            return output, history
        if feedback is not None:
            current_input = f"{task}\n\nFeedback from previous attempt:\n{feedback}"
    return output, history


async def _evaluate_exit_condition(
    exit_condition: str | None,
    task: str,
    output: str,
    reflector: LoopReflector | None,
) -> tuple[bool, str | None]:
    """Evaluate the configured rule and return convergence plus optional feedback."""
    if exit_condition == "llm" or (exit_condition is None and reflector is not None):
        if reflector is None:
            raise WorkflowError("loop exit_condition 'llm' requires a reflector")
        assessment = await reflector.assess(task, output)
        return not assessment.should_retry, assessment.feedback
    if exit_condition is None:
        return "DONE" in output, None
    match = re.fullmatch(r"output contains ['\"](.+)['\"]", exit_condition)
    if match is None:
        raise WorkflowError(f"unsupported loop exit_condition: {exit_condition}")
    return match.group(1) in output, None
