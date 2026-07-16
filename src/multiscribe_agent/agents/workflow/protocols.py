"""Injected boundaries used by the workflow engine."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AgentStepExecutor(Protocol):
    """Execute one agent workflow step by its definition ID."""

    async def execute(self, agent_id: str, user_input: str) -> str:
        """Return text output for the requested agent step."""


class LoopAssessment(Protocol):
    """The part of a reflection result consumed by a workflow loop."""

    feedback: str
    should_retry: bool


class LoopReflector(Protocol):
    """Assess one loop output through an injected adaptation boundary."""

    async def assess(self, task: str, output: str) -> LoopAssessment:
        """Return retry guidance for a completed loop iteration."""
