"""Tests for per-model daily usage persistence."""

from __future__ import annotations

import pytest

from multiscribe_agent.infra.db import init_db
from multiscribe_agent.infra.db_protocol import PlaceholderStyle
from multiscribe_agent.infra.repositories.daily_usage_by_model import (
    DailyUsageByModelRepository,
)


class _PostgresCapture:
    """Capture translated SQL without requiring a live PostgreSQL server."""

    placeholder_style = PlaceholderStyle.DOLLAR

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, statement: str, parameters: tuple[object, ...] = ()) -> int:
        """Record one translated statement."""
        self.executed.append((statement, parameters))
        return 1

    async def fetchall(
        self, statement: str, parameters: tuple[object, ...] = ()
    ) -> list[dict[str, object]]:
        """Return no rows after recording the translated query."""
        self.executed.append((statement, parameters))
        return []


@pytest.mark.asyncio
async def test_daily_usage_by_model_lazily_creates_and_accumulates() -> None:
    """Model buckets are created on first write and incremented on repeated writes."""
    db = await init_db(":memory:")
    try:
        repository = DailyUsageByModelRepository(db)
        assert (
            await db.fetchone("SELECT name FROM sqlite_master WHERE name = 'daily_usage_by_model'")
            is None
        )
        await repository.upsert(
            "2026-08-03",
            {
                "gpt-4o": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "total_tokens": 120,
                    "llm_calls": 1,
                }
            },
        )
        await repository.upsert(
            "2026-08-03",
            {
                "gpt-4o": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                    "llm_calls": 1,
                },
                "unknown": {
                    "input_tokens": 2,
                    "output_tokens": 1,
                    "total_tokens": 3,
                    "llm_calls": 1,
                },
            },
        )

        rows = await repository.query("2026-08-03", "2026-08-03")
        assert [(row.model_name, row.total_tokens) for row in rows] == [
            ("gpt-4o", 135),
            ("unknown", 3),
        ]
        assert rows[0].llm_calls == 2
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_daily_usage_by_model_query_is_inclusive_and_sorted() -> None:
    """Date filtering is inclusive and newest dates sort first."""
    db = await init_db(":memory:")
    try:
        repository = DailyUsageByModelRepository(db)
        await repository.upsert("2026-08-01", {"gpt-4o": {"total_tokens": 1}})
        await repository.upsert("2026-08-02", {"gpt-4o-mini": {"total_tokens": 5}})
        dates = [row.date for row in await repository.query("2026-08-01", "2026-08-02")]
        assert dates == ["2026-08-02", "2026-08-01"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_daily_usage_by_model_translates_postgres_sql_without_live_database() -> None:
    """PostgreSQL receives numbered binds and a composite conflict target."""
    database = _PostgresCapture()
    repository = DailyUsageByModelRepository(database)  # type: ignore[arg-type]

    await repository.upsert(
        "2026-08-03",
        {"gpt-4o": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}},
    )
    await repository.query("2026-08-01", "2026-08-03")

    upsert_sql = database.executed[1][0]
    query_sql = database.executed[2][0]
    assert "VALUES ($1, $2, $3, $4, $5, $6)" in upsert_sql
    assert "ON CONFLICT (date, model_name) DO UPDATE" in upsert_sql
    assert "date >= $1 AND date <= $2" in query_sql
