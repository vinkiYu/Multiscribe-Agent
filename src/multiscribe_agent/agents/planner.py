"""Basic LLM-backed task planner for optional Harness flows."""

from __future__ import annotations

import json

from multiscribe_agent.domain.models import AIMessage
from multiscribe_agent.llm.provider import AIProvider

PLANNER_INSTRUCTION = """Break the task into a short ordered list of executable steps.
Return only a JSON array of non-empty strings. Do not include Markdown fences."""


class Planner:
    """Ask an LLM to split a complex task into ordered steps."""

    async def plan(self, task: str, provider: AIProvider) -> list[str]:
        """Return validated non-empty planning steps from a provider response."""
        response = await provider.generate(
            [AIMessage(role="user", content=task)], system_instruction=PLANNER_INSTRUCTION
        )
        try:
            payload = json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise ValueError("planner response must be a JSON array") from exc
        if not isinstance(payload, list) or not all(isinstance(step, str) for step in payload):
            raise ValueError("planner response must be a JSON array of strings")
        steps = [step.strip() for step in payload if step.strip()]
        if not steps:
            raise ValueError("planner response must contain at least one step")
        return steps
