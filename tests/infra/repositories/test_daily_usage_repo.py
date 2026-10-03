from __future__ import annotations

import pytest

from multiscribe_agent.infra.repositories.daily_usage import DailyUsageRepository
from tests.db import init_test_database


@pytest.mark.asyncio
async def test_daily_usage_lazily_creates_and_accumulates() -> None:
    db = await init_test_database()
    try:
        repository = DailyUsageRepository(db)
        # The shared test database persists tables across tests; drop first so the
        # lazy-create probe observes the same pre-existence state as a fresh database.
        await db.execute("DROP TABLE IF EXISTS daily_usage")
        probe = await db.fetchone("SELECT to_regclass('public.daily_usage') AS name")
        assert probe is not None
        assert probe["name"] is None
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
    db = await init_test_database()
    try:
        repository = DailyUsageRepository(db)
        for date in ("2026-07-27", "2026-07-28", "2026-07-29"):
            await repository.upsert(date, {})
        dates = [row.date for row in await repository.query("2026-07-28", "2026-07-29")]
        assert dates == ["2026-07-29", "2026-07-28"]
    finally:
        await db.close()
