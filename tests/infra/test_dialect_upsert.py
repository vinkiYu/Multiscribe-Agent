"""Regression tests for PostgreSQL upsert SQL generation."""

from __future__ import annotations

from dataclasses import replace

import pytest

from multiscribe_agent.agents.workflow.iteration_store import IterationRecord, IterationStore
from multiscribe_agent.infra.db_protocol import PostgresRepositoryMixin
from multiscribe_agent.infra.repositories.curation_evaluations import (
    CurationEvaluationRecord,
    CurationEvaluationRepository,
)
from tests.db import init_test_database


def test_postgres_upsert_sql_derives_update_columns() -> None:
    sql = PostgresRepositoryMixin._upsert_sql(
        table="settings", columns=("key", "value"), conflict_target=("key",)
    )
    assert sql == (
        "INSERT INTO settings (key, value) VALUES ($1, $2) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
    )


def test_postgres_upsert_sql_rejects_empty_update_set() -> None:
    with pytest.raises(ValueError, match="requires update columns"):
        PostgresRepositoryMixin._upsert_sql(
            table="settings", columns=("key",), conflict_target=("key",)
        )


@pytest.mark.asyncio
async def test_curation_evaluation_upsert_is_idempotent() -> None:
    db = await init_test_database()
    try:
        repository = CurationEvaluationRepository(db)
        record = CurationEvaluationRecord(
            workflow_run_id="run-1",
            date="2026-07-30",
            recorded_at=100,
            rounds=2,
            converged=True,
            exit_reason="threshold",
            final_score=9.0,
            score_delta=1.0,
            avg_iter_score=8.5,
            result_count=5,
            usage={"total_tokens": 13},
        )
        await repository.upsert(record)
        await repository.upsert(replace(record, recorded_at=200))
        rows = await repository.query()
        assert len(rows) == 1
        assert rows[0].recorded_at == 200
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_iteration_store_upsert_is_idempotent() -> None:
    db = await init_test_database()
    try:
        store = IterationStore(db)
        await store.append(
            IterationRecord("run-1", "step-1", 1, "first", 7.0, "retry", False, "feedback")
        )
        await store.append(
            IterationRecord("run-1", "step-1", 1, "second", 8.0, "done", True, "threshold")
        )
        latest = await store.latest_for_step("run-1", "step-1")
        assert latest is not None
        assert latest.output == "second"
        assert latest.score == 8.0
        assert latest.converged is True
    finally:
        await db.close()
