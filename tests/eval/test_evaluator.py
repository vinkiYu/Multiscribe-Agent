import json
from pathlib import Path

import pytest

from multiscribe_agent.domain.models import AIResponse
from multiscribe_agent.eval.evaluator import JudgeError, evaluate_sample, score_summary


class FakeProvider:
    def __init__(self, responses: list[dict[str, object] | str]) -> None:
        self.responses = iter(responses)

    async def generate(self, *_args: object, **_kwargs: object) -> AIResponse:
        response = next(self.responses)
        content = response if isinstance(response, str) else json.dumps(response)
        return AIResponse(content=content)


@pytest.mark.asyncio
async def test_score_summary_constructs_all_dimensions() -> None:
    scores = await score_summary(
        FakeProvider([{"accuracy": 9, "conciseness": 8, "format": 7, "overall": 8}]),
        "summary",
    )
    assert scores.accuracy == 9
    assert scores.overall == 8


@pytest.mark.asyncio
async def test_evaluate_sample_scores_three_dimensions(tmp_path: Path) -> None:
    state = {
        "summary": "summary",
        "selected_items": [{"tags": ["AI"]}],
        "rss_success_rate": 1.0,
        "llm_success_rate": 0.9,
        "publish_success_rate": 1.0,
    }
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    provider = FakeProvider(
        [
            {"accuracy": 8, "conciseness": 8, "format": 8, "overall": 8},
            {"relevance": 7, "matched": 1, "total": 1, "reason": "match"},
            {"stability": 9, "bottleneck": "", "reason": "stable"},
        ]
    )
    result = await evaluate_sample(provider, "sample", path, ["AI"])
    assert result.summary.overall == 8
    assert result.relevance.relevance == 7
    assert result.stability.stability == 9
    assert result.passed


@pytest.mark.asyncio
async def test_non_json_judge_response_raises() -> None:
    with pytest.raises(JudgeError, match="non-JSON"):
        await score_summary(FakeProvider(["not-json"]), "summary")


@pytest.mark.asyncio
async def test_invalid_judge_score_raises() -> None:
    with pytest.raises(JudgeError, match="integer"):
        await score_summary(
            FakeProvider([{"accuracy": 11, "conciseness": 8, "format": 7, "overall": 8}]),
            "summary",
        )
