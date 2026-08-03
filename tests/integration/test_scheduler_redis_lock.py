"""Real-Redis integration tests for the task-type scheduler lock.

These tests use Redis database 15 and skip automatically when Redis is not
available. Start the optional service with ``docker-compose up -d redis`` to
exercise the distributed lease against a real server.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from multiscribe_agent.domain.models import ScheduleTask, TaskLog
from multiscribe_agent.services.scheduler import SchedulerService
from multiscribe_agent.services.scheduler_lock import RedisSchedulerLock

REDIS_URL = "redis://localhost:6379/15"


class MemoryTaskLogs:
    """Minimal task-log repository for Redis integration tests."""

    def __init__(self) -> None:
        self.logs: list[TaskLog] = []

    async def create(self, log: TaskLog) -> str:
        """Store a task log and return its positional identifier."""
        self.logs.append(log)
        return str(len(self.logs))

    async def update(self, log_id: str, **fields: object) -> None:
        """Apply task-log lifecycle fields."""
        index = int(log_id) - 1
        self.logs[index] = self.logs[index].model_copy(update=fields)


class MemorySchedules:
    """Empty schedule source required by ``SchedulerService``."""

    async def list_all(self, table: str) -> list[dict[str, object]]:
        """Return no persisted schedules."""
        assert table == "schedules"
        return []


def _task(task_id: str, task_type: str = "daily_digest") -> ScheduleTask:
    """Build a schedule task, including test-only task types."""
    task = ScheduleTask(
        id=task_id,
        name=task_id,
        task_type="daily_digest",
        cron="0 0 * * *",
    )
    return task if task_type == "daily_digest" else task.model_copy(update={"task_type": task_type})


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    """Provide an isolated Redis DB or skip when Redis is unavailable."""
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        pytest.skip("Redis not available; run docker-compose up -d redis")
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_real_redis_same_task_type_different_ids_mutually_exclusive(
    redis_client: Redis,
) -> None:
    """Cron and manual daily digests race on one real task-type lease."""
    lock = RedisSchedulerLock(REDIS_URL, client=redis_client)
    service = SchedulerService(
        MemoryTaskLogs(),
        MemorySchedules(),
        lock=lock,
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

    cron = _task("daily-ai-news")
    manual = _task("manual-daily-digest")
    first = asyncio.create_task(service.execute_task(cron, callback))
    await started.wait()
    second = await service.execute_task(manual, callback)
    finish.set()
    first_result = await first

    assert first_result == {"result_count": 1}
    assert second is None
    assert calls == 1
    assert await redis_client.dbsize() == 0


@pytest.mark.redis
@pytest.mark.asyncio
async def test_real_redis_different_task_types_run_independently(redis_client: Redis) -> None:
    """Different task types acquire independent leases."""
    service = SchedulerService(
        MemoryTaskLogs(),
        MemorySchedules(),
        lock=RedisSchedulerLock(REDIS_URL, client=redis_client),
        lock_ttl_seconds=120,
    )
    calls: list[str] = []

    async def callback(task: ScheduleTask) -> dict[str, object]:
        calls.append(task.id)
        return {}

    await service.execute_task(_task("daily-ai-news"), callback)
    await service.execute_task(_task("cleanup", "maintenance"), callback)

    assert calls == ["daily-ai-news", "cleanup"]
    assert await redis_client.dbsize() == 0


@pytest.mark.redis
@pytest.mark.asyncio
async def test_real_redis_lock_released_after_completion_allows_rerun(
    redis_client: Redis,
) -> None:
    """A completed task releases its lease and can run again."""
    service = SchedulerService(
        MemoryTaskLogs(),
        MemorySchedules(),
        lock=RedisSchedulerLock(REDIS_URL, client=redis_client),
        lock_ttl_seconds=120,
    )
    calls = 0

    async def callback(_: ScheduleTask) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {}

    task = _task("daily-ai-news")
    await service.execute_task(task, callback)
    await service.execute_task(task, callback)

    assert calls == 2
    assert await redis_client.dbsize() == 0
