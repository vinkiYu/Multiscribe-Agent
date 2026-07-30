"""Regression tests for the cross-dialect upsert abstraction."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from multiscribe_agent.agents.workflow.iteration_store import IterationRecord, IterationStore
from multiscribe_agent.infra.db import init_db
from multiscribe_agent.infra.db_protocol import PlaceholderStyle
from multiscribe_agent.infra.dialect import (
    DialectRepositoryMixin,
    PgDialect,
    SqlDialect,
    UpsertStyle,
    upsert_clause,
)
from multiscribe_agent.infra.repositories.curation_evaluations import (
    CurationEvaluationRecord,
    CurationEvaluationRepository,
)


class _Repository(DialectRepositoryMixin):
    """Small repository shell used to exercise SQL generation in isolation."""

    def __init__(self, style: PlaceholderStyle) -> None:
        self._db = SimpleNamespace(placeholder_style=style)


def test_upsert_clause_supports_targeted_and_primary_key_conflicts() -> None:
    assert (
        upsert_clause(
            UpsertStyle.ON_CONFLICT_DO_UPDATE,
            conflict_target=("id",),
            update_columns=("name", "value"),
        )
        == " ON CONFLICT (id) DO UPDATE SET name = excluded.name, value = excluded.value"
    )
    assert (
        upsert_clause(
            UpsertStyle.ON_CONFLICT_DO_NOTHING,
            conflict_target=("id",),
        )
        == " ON CONFLICT (id) DO NOTHING"
    )
    assert (
        upsert_clause(
            UpsertStyle.ON_CONFLICT_DO_NOTHING,
        )
        == " ON CONFLICT DO NOTHING"
    )


def test_upsert_clause_rejects_empty_update_set() -> None:
    with pytest.raises(ValueError, match="at least one update column"):
        upsert_clause(UpsertStyle.ON_CONFLICT_DO_UPDATE, conflict_target=("id",))


@pytest.mark.parametrize(
    ("style", "expected"),
    [
        (UpsertStyle.ON_CONFLICT_DO_UPDATE, " ON CONFLICT (id) DO UPDATE SET name = excluded.name"),
        (UpsertStyle.ON_CONFLICT_DO_NOTHING, " ON CONFLICT (id) DO NOTHING"),
        (UpsertStyle.INSERT_OR_REPLACE, " OR REPLACE"),
        (UpsertStyle.INSERT_OR_IGNORE, " OR IGNORE"),
    ],
)
def test_sqlite_render_upsert_supports_all_styles(style: UpsertStyle, expected: str) -> None:
    assert (
        SqlDialect.render_upsert(
            style,
            columns=("id", "name"),
            conflict_target=("id",),
            update_columns=("name",),
        )
        == expected
    )


def test_sqlite_render_upsert_derives_update_columns() -> None:
    assert (
        SqlDialect.render_upsert(
            UpsertStyle.ON_CONFLICT_DO_UPDATE,
            columns=("id", "name", "value"),
            conflict_target=("id",),
        )
        == " ON CONFLICT (id) DO UPDATE SET name = excluded.name, value = excluded.value"
    )


@pytest.mark.parametrize(
    "style",
    [UpsertStyle.ON_CONFLICT_DO_UPDATE, UpsertStyle.ON_CONFLICT_DO_NOTHING],
)
def test_postgres_render_upsert_supports_on_conflict_styles(style: UpsertStyle) -> None:
    result = PgDialect.render_upsert(
        style,
        columns=("id", "name"),
        conflict_target=("id",),
        update_columns=("name",),
    )
    assert result.startswith(" ON CONFLICT (id)")


@pytest.mark.parametrize("style", [UpsertStyle.INSERT_OR_REPLACE, UpsertStyle.INSERT_OR_IGNORE])
def test_postgres_render_upsert_rejects_sqlite_only_styles(style: UpsertStyle) -> None:
    with pytest.raises(NotImplementedError, match=style.value):
        PgDialect.render_upsert(style, columns=("id",))


def test_repository_upsert_sql_is_ready_for_placeholder_translation() -> None:
    repository = _Repository(PlaceholderStyle.DOLLAR)
    sql = repository._upsert_sql(
        table="settings",
        columns=("key", "value"),
        style=UpsertStyle.ON_CONFLICT_DO_UPDATE,
        conflict_target=("key",),
        update_columns=("value",),
    )
    assert sql == (
        "INSERT INTO settings (key, value) VALUES (?, ?)"
        " ON CONFLICT (key) DO UPDATE SET value = excluded.value"
    )
    assert repository._dialect.translate(sql).count("$") == 2


@pytest.mark.asyncio
async def test_curation_evaluation_upsert_is_idempotent() -> None:
    db = await init_db(":memory:")
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
    db = await init_db(":memory:")
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
