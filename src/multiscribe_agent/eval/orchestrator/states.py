"""Typed state contracts for the P64.3 six-step evaluation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class PipelineStep(StrEnum):
    """The sequential stages in one weekly evaluation cycle."""

    COLLECT = "collect"
    CLEAN = "clean"
    BENCH = "bench"
    GATE = "gate"
    ANALYZE = "analyze"
    FEEDBACK = "feedback"


class StepStatus(StrEnum):
    """Terminal or in-progress status for one pipeline stage."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class PipelineStepResult:
    """Inspectable outcome for one stage without carrying raw prompt/provider data."""

    step: PipelineStep
    status: StepStatus
    detail: str = ""
    artifact_paths: tuple[str, ...] = ()


@dataclass(slots=True)
class PipelineReport:
    """Full state-machine result for a weekly eval run."""

    run_id: str
    started_at: datetime
    dry_run: bool
    steps: dict[PipelineStep, PipelineStepResult] = field(default_factory=dict)
    finished_at: datetime | None = None
    feedback: str = ""

    @property
    def succeeded(self) -> bool:
        """Return whether every stage either succeeded or was deliberately skipped."""
        return all(
            result.status in {StepStatus.SUCCEEDED, StepStatus.SKIPPED}
            for result in self.steps.values()
        )


__all__ = ["PipelineReport", "PipelineStep", "PipelineStepResult", "StepStatus"]
