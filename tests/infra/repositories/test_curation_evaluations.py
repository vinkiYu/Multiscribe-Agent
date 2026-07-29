from __future__ import annotations

import pytest

from multiscribe_agent.infra.db import init_db
from multiscribe_agent.infra.repositories.curation_evaluations import (
    CurationEvaluationRecord,
    CurationEvaluationRepository,
)


def _record(
    run_id: str = "run-1",
    date: str = "2026-07-29",
    recorded_at: int = 100,
    *,
    converged: bool = True,
    exit_reason: str = "threshold",
    final_score: float | None = 9.0,
    rounds: int = 2,
) -> CurationEvaluationRecord:
    return CurationEvaluationRecord(
        workflow_run_id=run_id,
        date=date,
        recorded_at=recorded_at,
        rounds=rounds,
        converged=converged,
        exit_reason=exit_reason,
        final_score=final_score,
        score_delta=1.0,
        avg_iter_score=8.5,
        result_count=5,
        usage={"input_tokens": 10, "output_tokens": 3, "total_tokens": 13, "llm_calls": 2},
    )


@pytest.mark.asyncio
async def test_upsert_is_idempotent_per_workflow_run() -> None:
    db = await init_db(":memory:")
    try:
        repository = CurationEvaluationRepository(db)
        await repository.upsert(_record())
        await repository.upsert(_record(recorded_at=200))
        records = await repository.query()
        assert len(records) == 1
        assert records[0].recorded_at == 200
        assert records[0].usage["total_tokens"] == 13
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_query_filters_by_date_and_orders_newest_first() -> None:
    db = await init_db(":memory:")
    try:
        repository = CurationEvaluationRepository(db)
        await repository.upsert(_record("old", "2026-07-27", 100))
        await repository.upsert(_record("new", "2026-07-29", 300))
        records = await repository.query("2026-07-28", "2026-07-29")
        assert [record.workflow_run_id for record in records] == ["new"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_summary_returns_quality_convergence_and_exit_reason_metrics() -> None:
    db = await init_db(":memory:")
    try:
        repository = CurationEvaluationRepository(db)
        await repository.upsert(_record("good"))
        await repository.upsert(
            _record(
                "limited",
                recorded_at=200,
                rounds=3,
                converged=False,
                exit_reason="max_rounds",
                final_score=7.0,
            )
        )
        summary = await repository.summary("2026-07-29", "2026-07-29")
        assert summary["total_runs"] == 2
        assert summary["converged_runs"] == 1
        assert summary["avg_score"] == 8.0
        assert summary["converge_rate"] == 50.0
        assert summary["per_reason_counts"] == {"max_rounds": 1, "threshold": 1}
    finally:
        await db.close()
