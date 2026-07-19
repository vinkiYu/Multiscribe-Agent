"""Evaluation-driven refinement decisions for low-scoring workflow output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]

from multiscribe_agent.domain.models import WorkflowDefinition

RefinementAction = Literal["none", "retry", "switch_agent", "human_review"]


@dataclass(frozen=True, slots=True)
class RefinementDecision:
    """One decision returned by the feedback loop coordinator."""

    action: RefinementAction
    reason: str
    suggested_workflow: str | None
    score: float
    threshold: float
    dataset: str | None = None


def trigger_refinement(
    score: float,
    dataset: str | None = None,
    threshold: float = 7.0,
    *,
    workflows_dir: Path | None = None,
    preferred_workflow: str | None = "digest-retry",
) -> RefinementDecision:
    """Return the refinement action implied by an evaluation score."""
    if score >= threshold:
        return RefinementDecision(
            action="none",
            reason=f"score {score:.2f} meets threshold {threshold:.2f}",
            suggested_workflow=None,
            score=score,
            threshold=threshold,
            dataset=dataset,
        )
    if score >= threshold - 2.0:
        return RefinementDecision(
            action="retry",
            reason="score near threshold; retry with refinement feedback",
            suggested_workflow=preferred_workflow,
            score=score,
            threshold=threshold,
            dataset=dataset,
        )
    alternate = _first_workflow(workflows_dir)
    if alternate is not None:
        return RefinementDecision(
            action="switch_agent",
            reason=f"score {score:.2f} is far below threshold; try alternate workflow",
            suggested_workflow=alternate,
            score=score,
            threshold=threshold,
            dataset=dataset,
        )
    return RefinementDecision(
        action="human_review",
        reason="score is far below threshold and no alternate workflow is available",
        suggested_workflow=None,
        score=score,
        threshold=threshold,
        dataset=dataset,
    )


def load_refinement_workflow(name: str, workflows_dir: Path) -> WorkflowDefinition:
    """Load a YAML workflow definition by stem, for example digest-retry."""
    path = workflows_dir / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"workflow not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return WorkflowDefinition.model_validate(raw)


def _first_workflow(workflows_dir: Path | None) -> str | None:
    if workflows_dir is None or not workflows_dir.is_dir():
        return None
    candidate = next(iter(sorted(workflows_dir.glob("*.yaml"))), None)
    return candidate.stem if candidate is not None else None
