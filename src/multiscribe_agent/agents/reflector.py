"""Basic output reflection for the first Harness feedback loop."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, cast

from multiscribe_agent.domain.models import AIMessage
from multiscribe_agent.llm.provider import AIProvider

REFLECTOR_INSTRUCTION = """Assess whether the output satisfies the task.
Return only JSON: {"quality":"pass|fail","score":0.0,"feedback":"..."}.
The score must be between 0 and 10 (integers or 0.5 increments).
Do not include Markdown fences."""


@dataclass(frozen=True, slots=True)
class Reflection:
    """Structured quality assessment used to decide whether to retry."""

    quality: Literal["pass", "fail"]
    score: float
    feedback: str
    should_retry: bool


class Reflector:
    """Ask an LLM to assess an output and produce actionable feedback."""

    async def assess(self, task: str, output: str, provider: AIProvider) -> Reflection:
        """Return a validated reflection whose retry flag follows its quality."""
        prompt = f"Task:\n{task}\n\nOutput:\n{output}"
        response = await provider.generate(
            [AIMessage(role="user", content=prompt)],
            system_instruction=REFLECTOR_INSTRUCTION,
        )
        try:
            payload = json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise ValueError("reflector response must be a JSON object") from exc
        if not isinstance(payload, dict):
            raise ValueError("reflector response must be a JSON object")
        quality = payload.get("quality")
        score = payload.get("score")
        feedback = payload.get("feedback")
        if quality not in {"pass", "fail"}:
            raise ValueError("reflection quality must be pass or fail")
        if not isinstance(score, int | float) or isinstance(score, bool):
            raise ValueError("reflection score must be numeric")
        if not 0 <= float(score) <= 10:
            raise ValueError("reflection score must be between 0 and 10")
        if not isinstance(feedback, str):
            raise ValueError("reflection feedback must be a string")
        typed_quality = cast(Literal["pass", "fail"], quality)
        return Reflection(
            quality=typed_quality,
            score=float(score),
            feedback=feedback,
            should_retry=typed_quality == "fail",
        )
