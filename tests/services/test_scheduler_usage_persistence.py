from __future__ import annotations

import pytest

from multiscribe_agent.domain.models import ScheduleTask, TaskLog
from multiscribe_agent.infra.db import init_db
from multiscribe_agent.infra.repositories.daily_usage import DailyUsageRepository
from multiscribe_agent.services.scheduler import SchedulerService


class _Logs:
    def __init__(self) -> None:
        self.rows: dict[str, TaskLog] = {}

    async def create(self, log: TaskLog) -> str:
        key = str(len(self.rows) + 1)
        self.rows[key] = log.model_copy(update={"id": key})
        return key

    async def update(self, log_id: str, **fields: object) -> None:
        self.rows[log_id] = self.rows[log_id].model_copy(update=fields)

    async def get(self, log_id: str) -> TaskLog | None:
        return self.rows.get(log_id)


class _Schedules:
    async def list_all(self, table: str) -> list[dict[str, object]]:
        del table
        return []


@pytest.mark.asyncio
async def test_scheduler_persists_usage_and_keeps_legacy_results_compatible() -> None:
    db = await init_db(":memory:")
    try:
        usage = DailyUsageRepository(db)
        scheduler = SchedulerService(_Logs(), _Schedules(), daily_usage_repo=usage)
        task = ScheduleTask(id="daily", name="Daily", task_type="daily_digest", cron="0 9 * * *")

        async def callback(_: ScheduleTask) -> dict[str, object]:
            return {
                "result_count": 3,
                "usage": {
                    "input_tokens": 8,
                    "output_tokens": 2,
                    "total_tokens": 10,
                    "llm_calls": 1,
                },
            }

        await scheduler.execute_task(task, callback)
        records = await usage.query("2000-01-01", "2999-12-31")
        assert records[0].total_tokens == 10

        await scheduler.execute_task(task, lambda _: _empty_result())
        assert records[0].task_count == 1
    finally:
        await db.close()


async def _empty_result() -> dict[str, object]:
    return {}
