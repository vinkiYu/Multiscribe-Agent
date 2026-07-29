"""Optional LLM-as-judge support for post-loop daily curation evaluation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from multiscribe_agent.domain.models import AIMessage
from multiscribe_agent.llm.provider import AIProvider

CURATOR_JUDGE_INSTRUCTION = """Evaluate the quality of a curated daily-news selection.
Return only JSON: {"score": 0.0, "feedback": "...", "passed": true|false}.
Score must be from 0 to 10. Judge relevance, diversity, factual grounding, and concise summaries."""


@dataclass(frozen=True, slots=True)
class CuratorJudgeConfig:
    """Controls optional post-loop LLM assessment cost and invocation scope."""

    enabled: bool = False
    scope: Literal["always", "on_converge", "on_failure"] = "on_converge"


class CuratorJudge:
    """Run a separately configurable, opt-in curation quality assessment."""

    def __init__(self, config: CuratorJudgeConfig | None = None) -> None:
        self._config = config or CuratorJudgeConfig()

    async def evaluate(
        self,
        curated: list[dict[str, object]],
        loop_summary: Mapping[str, object],
        provider: AIProvider,
    ) -> dict[str, object] | None:
        """Return validated judge output only when this run matches the configured scope."""
        if not self._config.enabled or not self._matches_scope(loop_summary):
            return None
        response = await provider.generate(
            [
                AIMessage(
                    role="user",
                    content=json.dumps(
                        {"curated": curated, "loop_summary": dict(loop_summary)}, ensure_ascii=False
                    ),
                )
            ],
            system_instruction=CURATOR_JUDGE_INSTRUCTION,
        )
        return _validated_response(response.content)

    def _matches_scope(self, loop_summary: Mapping[str, object]) -> bool:
        if self._config.scope == "always":
            return True
        converged = bool(loop_summary.get("converged"))
        return converged if self._config.scope == "on_converge" else not converged


def _validated_response(content: str) -> dict[str, object]:
    """Parse the narrow public JSON contract returned by the judge model."""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("curator judge response must be a JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("curator judge response must be a JSON object")
    score = payload.get("score")
    feedback = payload.get("feedback")
    passed = payload.get("passed")
    if not isinstance(score, int | float) or isinstance(score, bool) or not 0 <= score <= 10:
        raise ValueError("curator judge score must be between 0 and 10")
    if not isinstance(feedback, str):
        raise ValueError("curator judge feedback must be a string")
    if not isinstance(passed, bool):
        raise ValueError("curator judge passed must be a boolean")
    return {"score": float(score), "feedback": feedback, "passed": passed}
