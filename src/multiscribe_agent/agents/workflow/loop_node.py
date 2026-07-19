"""Bounded workflow loop execution with multi-round self-evaluation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from multiscribe_agent.agents.workflow.protocols import AgentStepExecutor, LoopReflector
from multiscribe_agent.core.errors import WorkflowError
from multiscribe_agent.domain.models import WorkflowStep


@dataclass(frozen=True, slots=True)
class LoopSpec:
    """Configuration for a multi-round self-evaluating loop step."""

    max_rounds: int = 3
    score_threshold: float = 8.0
    convergence_delta: float = 0.5
    min_score: float = 0.0
    max_score: float = 10.0


@dataclass(frozen=True, slots=True)
class LoopIteration:
    """One loop iteration with score, delta, feedback, and exit reason."""

    round: int
    output: str
    score: float | None
    delta: float | None
    feedback: str | None
    converged: bool
    reason: str


def _coerce_loop_spec(step: WorkflowStep) -> LoopSpec:
    """Read optional overrides from step.config while preserving max_iterations."""
    raw_config = step.config.get("loop", step.config)
    config = raw_config if isinstance(raw_config, dict) else {}
    spec = LoopSpec(
        max_rounds=int(config.get("max_rounds", step.max_iterations or 3)),
        score_threshold=float(config.get("score_threshold", 8.0)),
        convergence_delta=float(config.get("convergence_delta", 0.5)),
    )
    if spec.max_rounds <= 0:
        raise WorkflowError("loop max_rounds must be positive")
    if spec.convergence_delta < 0:
        raise WorkflowError("loop convergence_delta must not be negative")
    if not spec.min_score <= spec.score_threshold <= spec.max_score:
        raise WorkflowError("loop score_threshold must be between 0 and 10")
    return spec


async def execute_loop_step(
    step: WorkflowStep,
    step_input: str,
    executor: AgentStepExecutor,
    reflector: LoopReflector | None,
    *,
    trace_id: str,
) -> tuple[str, list[dict[str, object]]]:
    """Execute an agent step until score, convergence, rule, or round bound exits."""
    del trace_id
    if step.agent_id is None:
        raise WorkflowError("loop step requires agent_id")
    spec = _coerce_loop_spec(step)
    task = step_input
    current_input = step_input
    iterations: list[LoopIteration] = []
    output = ""
    for round_number in range(1, spec.max_rounds + 1):
        output = await executor.execute(step.agent_id, current_input)
        rule_converged, score, feedback = await _evaluate(
            step.exit_condition, task, output, reflector, spec
        )
        previous_score = iterations[-1].score if iterations else None
        score_delta = (
            abs(score - previous_score)
            if score is not None and previous_score is not None
            else None
        )
        reason = _classify_exit(spec, score, score_delta, round_number, rule_converged)
        converged = reason in {"threshold", "convergence", "condition"}
        iterations.append(
            LoopIteration(
                round=round_number,
                output=output,
                score=score,
                delta=score_delta,
                feedback=feedback,
                converged=converged,
                reason=reason,
            )
        )
        if reason in {"threshold", "convergence", "condition", "max_rounds"}:
            break
        if feedback is not None:
            current_input = f"{task}\n\nFeedback from previous attempt:\n{feedback}"
    return output, [_dump_iteration(iteration) for iteration in iterations]


async def _evaluate(
    exit_condition: str | None,
    task: str,
    output: str,
    reflector: LoopReflector | None,
    spec: LoopSpec,
) -> tuple[bool, float | None, str | None]:
    """Return (condition_converged, score, feedback) for one loop round."""
    if exit_condition == "llm" or (exit_condition is None and reflector is not None):
        if reflector is None:
            raise WorkflowError("loop exit_condition 'llm' requires a reflector")
        assessment = await reflector.assess(task, output)
        score = _score_from_assessment(assessment, spec)
        return score > spec.score_threshold, score, assessment.feedback
    if exit_condition is None:
        return "DONE" in output, None, None
    match = re.fullmatch(r"output contains ['\"](.+)['\"]", exit_condition)
    if match is None:
        raise WorkflowError(f"unsupported loop exit_condition: {exit_condition}")
    return match.group(1) in output, None, None


def _score_from_assessment(assessment: object, spec: LoopSpec) -> float:
    """Read a 0-10 assessment score while tolerating pre-P24 reflector stubs."""
    raw = getattr(assessment, "score", None)
    if raw is None:
        should_retry = bool(getattr(assessment, "should_retry", True))
        return spec.min_score if should_retry else spec.max_score
    if not isinstance(raw, int | float) or isinstance(raw, bool):
        raise WorkflowError("loop reflector score must be numeric")
    score = float(raw)
    if not spec.min_score <= score <= spec.max_score:
        raise WorkflowError("loop reflector score must be between 0 and 10")
    return score


def _classify_exit(
    spec: LoopSpec,
    score: float | None,
    score_delta: float | None,
    round_number: int,
    condition_converged: bool,
) -> str:
    """Describe why an iteration stopped or continued."""
    if condition_converged and score is not None:
        return "threshold"
    if condition_converged:
        return "condition"
    if score_delta is not None and score_delta < spec.convergence_delta:
        return "convergence"
    if round_number >= spec.max_rounds:
        return "max_rounds"
    if score is not None and score <= spec.min_score + 1:
        return "stuck"
    return "continue"


def _dump_iteration(iteration: LoopIteration) -> dict[str, object]:
    """Serialize one loop iteration for workflow history storage."""
    return {
        "iteration": iteration.round,
        "output": iteration.output,
        "score": iteration.score,
        "delta": iteration.delta,
        "feedback": iteration.feedback,
        "converged": iteration.converged,
        "reason": iteration.reason,
    }
