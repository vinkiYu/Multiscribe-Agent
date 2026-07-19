"""LLM-as-Judge evaluator with three scoring dimensions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from multiscribe_agent.domain.models import AIMessage
from multiscribe_agent.eval.judge_prompts import (
    RELEVANCE_RUBRIC,
    STABILITY_RUBRIC,
    SUMMARY_RUBRIC,
)
from multiscribe_agent.llm.provider import AIProvider


@dataclass(frozen=True, slots=True)
class SummaryScores:
    """Summary quality dimensions, scored from 0 to 10."""

    accuracy: int
    conciseness: int
    format: int
    overall: int


@dataclass(frozen=True, slots=True)
class RelevanceScores:
    """Recommendation relevance dimensions, scored from 0 to 10."""

    relevance: int
    matched: int
    total: int
    reason: str


@dataclass(frozen=True, slots=True)
class StabilityScores:
    """Pipeline stability score and judge explanation."""

    stability: int
    bottleneck: str
    reason: str


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """All judge dimensions for one replayed sample."""

    sample_id: str
    summary: SummaryScores
    relevance: RelevanceScores
    stability: StabilityScores
    passed: bool

    @property
    def overall(self) -> float:
        """Return the mean score used by benchmark summaries."""
        return (self.summary.overall + self.relevance.relevance + self.stability.stability) / 3.0


class JudgeError(ValueError):
    """Raised when the LLM-as-Judge response cannot be parsed."""


async def _ask_judge(provider: AIProvider, prompt: str, system: str) -> dict[str, object]:
    response = await provider.generate(
        [AIMessage(role="user", content=prompt)],
        system_instruction=system,
    )
    try:
        payload = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise JudgeError(f"Judge returned non-JSON: {response.content!r}") from exc
    if not isinstance(payload, dict):
        raise JudgeError("Judge payload must be a JSON object")
    return payload


def _score(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 10:
        raise JudgeError(f"Judge field {key!r} must be an integer from 0 to 10")
    return value


async def score_summary(provider: AIProvider, summary: str) -> SummaryScores:
    payload = await _ask_judge(provider, f"Summary to evaluate:\n{summary}", SUMMARY_RUBRIC)
    return SummaryScores(
        accuracy=_score(payload, "accuracy"),
        conciseness=_score(payload, "conciseness"),
        format=_score(payload, "format"),
        overall=_score(payload, "overall"),
    )


async def score_relevance(
    provider: AIProvider,
    preferred_tags: list[str],
    item_tags: list[str],
) -> RelevanceScores:
    prompt = RELEVANCE_RUBRIC.format(tags=preferred_tags, item_tags=item_tags)
    payload = await _ask_judge(provider, prompt, "You are a relevance auditor.")
    matched = payload.get("matched")
    total = payload.get("total")
    if not isinstance(matched, int) or isinstance(matched, bool) or matched < 0:
        raise JudgeError("Judge field 'matched' must be a non-negative integer")
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise JudgeError("Judge field 'total' must be a non-negative integer")
    return RelevanceScores(
        relevance=_score(payload, "relevance"),
        matched=matched,
        total=total,
        reason=str(payload.get("reason", "")),
    )


async def score_stability(
    provider: AIProvider,
    stats: dict[str, float | int],
) -> StabilityScores:
    payload = await _ask_judge(provider, STABILITY_RUBRIC.format(stats=stats), "You are an SRE.")
    return StabilityScores(
        stability=_score(payload, "stability"),
        bottleneck=str(payload.get("bottleneck", "")),
        reason=str(payload.get("reason", "")),
    )


async def evaluate_sample(
    provider: AIProvider,
    sample_id: str,
    pipeline_state_path: Path,
    preferred_tags: list[str],
) -> EvaluationResult:
    """Read pipeline-state JSON and produce three-dimension scores."""
    try:
        state = json.loads(pipeline_state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JudgeError(f"invalid pipeline state {pipeline_state_path}: {exc}") from exc
    if not isinstance(state, dict):
        raise JudgeError("pipeline state must be a JSON object")
    summary_text = state.get("summary")
    if not isinstance(summary_text, str):
        raise JudgeError("pipeline state summary must be a string")
    selected_items = state.get("selected_items", [])
    if not isinstance(selected_items, list):
        raise JudgeError("pipeline state selected_items must be a list")
    item_tags = [
        tag
        for item in selected_items
        if isinstance(item, dict)
        for tag in item.get("tags", [])
        if isinstance(tag, str)
    ]

    summary = await score_summary(provider, summary_text)
    relevance = await score_relevance(provider, preferred_tags, item_tags)
    stats = {
        "rss_success": _number(state.get("rss_success_rate", 0.0)),
        "llm_success": _number(state.get("llm_success_rate", 0.0)),
        "publish_success": _number(state.get("publish_success_rate", 0.0)),
    }
    stability = await score_stability(provider, stats)

    overall = (summary.overall + relevance.relevance + stability.stability) / 3.0
    return EvaluationResult(
        sample_id=sample_id,
        summary=summary,
        relevance=relevance,
        stability=stability,
        passed=overall >= 7.0,
    )


def _number(value: object) -> float | int:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return 0.0
