from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from multiscribe_agent.agents.curator_judge import CuratorJudge, CuratorJudgeConfig
from multiscribe_agent.agents.pipelines.daily_digest import DailyDigestConfig, DailyDigestPipeline
from multiscribe_agent.domain.models import AIResponse, SourceData
from multiscribe_agent.infra.db import init_db
from multiscribe_agent.infra.repositories.curation_evaluations import CurationEvaluationRepository


class _Provider:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, *args: object, **kwargs: object) -> AIResponse:
        del args, kwargs
        self.calls += 1
        return AIResponse(content='{"score": 9, "feedback": "grounded", "passed": true}')


class _Ingestion:
    async def run_all(self, configs: list[dict[str, object]]) -> dict[str, int]:
        del configs
        return {"rss": 1}


class _Sources:
    async def get_by_date_range(
        self, start: str, end: str, query_field: str = "ingestion_date"
    ) -> list[SourceData]:
        del start, end, query_field
        return [
            SourceData(
                id="one",
                title="One",
                url="https://example.test/one",
                description="One description",
                published_date="2026-07-29T08:00:00+00:00",
                source="RSS",
                category="technology",
                fetched_at="2026-07-29T08:01:00+00:00",
                ingestion_date="2026-07-29T08:01:00+00:00",
                adapter_name="rss",
            )
        ]


class _Curator:
    async def execute(self, agent_id: str, user_input: str) -> str:
        del user_input
        if agent_id == "curator":
            return json.dumps([{"id": "one", "title": "One", "summary": "Summary", "score": 9}])
        return "Overview"


class _Publishing:
    async def fanout(self, digest: object, targets: list[str]) -> dict[str, dict[str, object]]:
        del digest, targets
        return {}


@dataclass(frozen=True)
class _Assessment:
    score: float = 9.0
    feedback: str = "looks good"
    should_retry: bool = False


class _Reflector:
    async def assess(self, task: str, output: str) -> _Assessment:
        del task, output
        return _Assessment()


@pytest.mark.asyncio
async def test_curator_judge_is_disabled_by_default_without_provider_call() -> None:
    provider = _Provider()
    result = await CuratorJudge().evaluate([], {"converged": True}, provider)  # type: ignore[arg-type]
    assert result is None
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_curator_judge_validates_enabled_response() -> None:
    provider = _Provider()
    judge = CuratorJudge(CuratorJudgeConfig(enabled=True, scope="on_converge"))
    result = await judge.evaluate([], {"converged": True}, provider)  # type: ignore[arg-type]
    assert result == {"score": 9.0, "feedback": "grounded", "passed": True}
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_daily_digest_returns_loop_summary_and_workflow_run_id() -> None:
    pipeline = DailyDigestPipeline(
        _Ingestion(),
        _Sources(),  # type: ignore[arg-type]
        _Curator(),  # type: ignore[arg-type]
        _Publishing(),  # type: ignore[arg-type]
        DailyDigestConfig(curate_agent_id="curator", adapter_ids=["rss"], top_n=1, targets=[]),
        _Reflector(),  # type: ignore[arg-type]
    )
    result = await pipeline.run(run_date="2026-07-29")
    summary = result["loop_summary"]
    assert isinstance(summary, dict)
    assert summary["rounds"] == 1
    assert summary["converged"] is True
    assert summary["exit_reason"] == "threshold"
    assert summary["final_score"] == 9.0
    workflow_run_id = result["workflow_run_id"]
    assert isinstance(workflow_run_id, str)
    assert workflow_run_id


@pytest.mark.asyncio
async def test_daily_digest_persists_one_evaluation_per_workflow_run() -> None:
    db = await init_db(":memory:")
    try:
        evaluations = CurationEvaluationRepository(db)
        pipeline = DailyDigestPipeline(
            _Ingestion(),
            _Sources(),  # type: ignore[arg-type]
            _Curator(),  # type: ignore[arg-type]
            _Publishing(),  # type: ignore[arg-type]
            DailyDigestConfig(curate_agent_id="curator", adapter_ids=["rss"], top_n=1, targets=[]),
            _Reflector(),  # type: ignore[arg-type]
            db=db,
            curation_evaluations=evaluations,
        )
        result = await pipeline.run(run_date="2026-07-29")
        records = await evaluations.query("2026-07-29", "2026-07-29")
        assert len(records) == 1
        assert records[0].workflow_run_id == result["workflow_run_id"]
        assert records[0].final_score == 9.0
    finally:
        await db.close()
