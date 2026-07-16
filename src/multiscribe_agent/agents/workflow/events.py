"""Workflow lifecycle event contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

WorkflowEventType = Literal[
    "workflow_start",
    "step_start",
    "step_complete",
    "step_error",
    "loop_iteration",
    "workflow_complete",
    "workflow_error",
]


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    """One structured event emitted by a workflow run."""

    type: WorkflowEventType
    data: dict[str, object]
    trace_id: str
