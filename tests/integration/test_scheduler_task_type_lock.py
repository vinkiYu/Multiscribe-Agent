"""Integration coverage for the shared task-type scheduler lock."""

from __future__ import annotations

import asyncio

import pytest

from multiscribe_agent.domain.models import ScheduleTask, TaskLog
from multiscribe_agent.services.scheduler import SchedulerService
from multiscribe_agent.services.scheduler_lock import RedisSchedulerLock


class MemoryTaskLogs:
    """Minimal task-log repository for the scheduler integration test."""

    def __init__(self) -> None:
        self.logs: list[TaskLog] = []

    async def create(self, log: TaskLog) -> str:
        self.logs.append(log)
        return str(len(self.logs))

    async def update(self, log_id: str, **fields: object) -> None:
        self.logs[int(log_id) - 1] = self.logs[int(log_id) - 1].model_copy(update=fields)


class MemorySchedules:
    """Empty schedule source required by SchedulerService."""

    async def list_all(self, table: str) -> list[dict[str, object]]:
        assert table == "schedules"
        return []


class FakeRedis:
    """Small atomic set/eval surface matching RedisSchedulerLock's contract."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, name: str, value: str, *, ex: int, nx: bool) -> bool:
        del ex
        if nx and name in self.values:
            return False
        self.values[name] = value
        return True

    async def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
        del script, numkeys
        if self.values.get(key) != token:
            return 0
        del self.values[key]
        return 1


def _task(task_id: str) -> ScheduleTask:
    """Build one cron/manual task using the shared daily-digest type."""
    return ScheduleTask(
        id=task_id,
        name=task_id,
        task_type="daily_digest",
        cron="0 0 * * *",
    )


@pytest.mark.asyncio
async def test_cron_and_manual_daily_digest_share_redis_task_type_lock() -> None:
    """Different task IDs still produce one callback when they race on one day."""
    redis = FakeRedis()
    service = SchedulerService(
        MemoryTaskLogs(),
        MemorySchedules(),
        lock=RedisSchedulerLock("redis://unused", client=redis),
        lock_ttl_seconds=120,
    )
    started = asyncio.Event()
    finish = asyncio.Event()
    calls = 0

    async def callback(_: ScheduleTask) -> dict[str, object]:
        nonlocal calls
        calls += 1
        started.set()
        await finish.wait()
        return {"result_count": 1}

    first = asyncio.create_task(service.execute_task(_task("daily-ai-news"), callback))
    await started.wait()
    second = await service.execute_task(_task("manual-daily-digest"), callback)
    finish.set()
    first_result = await first

    assert first_result == {"result_count": 1}
    assert second is None
    assert calls == 1
    assert redis.values == {}
