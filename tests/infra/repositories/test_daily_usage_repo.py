from __future__ import annotations

import pytest

from multiscribe_agent.infra.db import init_db
from multiscribe_agent.infra.repositories.daily_usage import DailyUsageRepository


@pytest.mark.asyncio
async def test_daily_usage_lazily_creates_and_accumulates() -> None:
    db = await init_db(":memory:")
    try:
        repository = DailyUsageRepository(db)
        assert (
            await db.fetchone("SELECT name FROM sqlite_master WHERE name = 'daily_usage'") is None
        )
        await repository.upsert(
            "2026-07-29",
            {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14, "llm_calls": 1},
        )
        await repository.upsert(
            "2026-07-29",
            {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5, "llm_calls": 1},
        )
        rows = await repository.query("2026-07-29", "2026-07-29")
        assert rows[0].input_tokens == 12
        assert rows[0].output_tokens == 7
        assert rows[0].total_tokens == 19
        assert rows[0].llm_calls == 2
        assert rows[0].task_count == 2
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_daily_usage_query_is_inclusive_and_sorted() -> None:
    db = await init_db(":memory:")
    try:
        repository = DailyUsageRepository(db)
        for date in ("2026-07-27", "2026-07-28", "2026-07-29"):
            await repository.upsert(date, {})
        dates = [row.date for row in await repository.query("2026-07-28", "2026-07-29")]
        assert dates == ["2026-07-29", "2026-07-28"]
    finally:
        await db.close()
