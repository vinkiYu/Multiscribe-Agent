"""Tests for APScheduler orchestration and task-log lifecycle handling."""

from __future__ import annotations

import asyncio

import pytest

from multiscribe_agent.domain.models import ScheduleTask, TaskLog
from multiscribe_agent.services.scheduler import SchedulerService, TaskExecutorRegistry
from multiscribe_agent.services.scheduler_lock import AcquireResult


class MemoryTaskLogs:
    """Minimal in-memory task-log port for scheduler tests."""

    def __init__(self) -> None:
        self.logs: dict[str, TaskLog] = {}
        self._next_id = 1

    async def create(self, log: TaskLog) -> str:
        """Store a running log and return a stable ID."""
        log_id = str(self._next_id)
        self._next_id += 1
        self.logs[log_id] = log.model_copy(update={"id": log_id})
        return log_id

    async def update(self, log_id: str, **fields: object) -> None:
        """Apply task-log lifecycle fields."""
        self.logs[log_id] = self.logs[log_id].model_copy(update=fields)

    async def get(self, log_id: str) -> TaskLog | None:
        """Return a stored log."""
        return self.logs.get(log_id)


class MemorySchedules:
    """Minimal in-memory entity store for persisted schedules."""

    def __init__(self, tasks: list[ScheduleTask] | None = None) -> None:
        self.tasks = {task.id: task.model_dump() for task in tasks or []}

    async def list_all(self, table: str) -> list[dict[str, object]]:
        """Return all schedule documents."""
        assert table == "schedules"
        return list(self.tasks.values())


def task(task_id: str = "daily") -> ScheduleTask:
    """Build a valid daily-digest schedule task."""
    return ScheduleTask(id=task_id, name="Daily", task_type="daily_digest", cron="0 9 * * *")


@pytest.mark.asyncio
async def test_register_run_now_and_unregister_create_complete_log() -> None:
    """Immediate execution calls the callback and records a successful lifecycle."""
    logs = MemoryTaskLogs()
    service = SchedulerService(logs, MemorySchedules())
    called: list[str] = []

    async def callback(scheduled: ScheduleTask) -> dict[str, object]:
        called.append(scheduled.id)
        return {"result_count": 2, "message": "done"}

    service.register(task(), callback)
    await service.run_now("daily")

    assert called == ["daily"]
    assert next(iter(logs.logs.values())).status == "success"
    assert next(iter(logs.logs.values())).result_count == 2
    service.unregister("daily")
    with pytest.raises(ValueError, match="unknown"):
        await service.run_now("daily")


@pytest.mark.asyncio
async def test_errors_missing_executor_reload_and_invalid_cron_are_isolated() -> None:
    """Failures create error logs and invalid cron never adds a job."""
    scheduled = task("reload")
    logs = MemoryTaskLogs()
    registry = TaskExecutorRegistry()
    service = SchedulerService(logs, MemorySchedules([scheduled]), executor_registry=registry)

    async def failing_callback(_: ScheduleTask) -> dict[str, object]:
        raise RuntimeError("boom")

    registry.register("daily_digest", failing_callback)
    await service.start()
    await service.run_now("reload")
    assert next(iter(logs.logs.values())).status == "error"
    await service.reload()
    assert "reload" in service._tasks
    with pytest.raises(ValueError, match="Wrong number of fields"):
        service.register(task("bad").model_copy(update={"cron": "bad cron"}), failing_callback)
    await service.stop()


class HoldingLock:
    """In-process lock fake that exposes concurrent acquisition behavior."""

    def __init__(self) -> None:
        self.held = False
        self.releases = 0

    async def acquire(self, key: str, ttl_seconds: int) -> AcquireResult:
        assert key.startswith("multiscribe:scheduler:lock:daily:")
        assert ttl_seconds == 120
        if self.held:
            return AcquireResult(acquired=False, reason="already_locked")
        self.held = True
        return AcquireResult(acquired=True, token="owner-token", reason="acquired")

    async def release(self, key: str, token: str) -> None:
        assert key.startswith("multiscribe:scheduler:lock:daily:")
        assert token == "owner-token"
        self.held = False
        self.releases += 1


class UnavailableLock:
    """Lock fake that models a Redis connection failure."""

    async def acquire(self, key: str, ttl_seconds: int) -> AcquireResult:
        del key, ttl_seconds
        raise ConnectionError("redis unavailable")

    async def release(self, key: str, token: str) -> None:
        del key, token


@pytest.mark.asyncio
async def test_lock_busy_is_skipped_without_calling_callback() -> None:
    """A concurrent second trigger gets a skipped terminal log."""
    logs = MemoryTaskLogs()
    lock = HoldingLock()
    service = SchedulerService(logs, MemorySchedules(), lock=lock, lock_ttl_seconds=120)
    started = asyncio.Event()
    finish = asyncio.Event()
    calls = 0

    async def callback(_: ScheduleTask) -> dict[str, object]:
        nonlocal calls
        calls += 1
        started.set()
        await finish.wait()
        return {}

    first = asyncio.create_task(service.execute_task(task(), callback))
    await started.wait()
    await service.execute_task(task(), callback)
    assert calls == 1
    assert any(log.status == "skipped" for log in logs.logs.values())

    finish.set()
    await first
    assert lock.releases == 1


@pytest.mark.asyncio
async def test_released_lock_allows_next_run_and_run_now_uses_same_guard() -> None:
    """The direct scheduler path and run_now share execute_task's lock boundary."""
    logs = MemoryTaskLogs()
    lock = HoldingLock()
    service = SchedulerService(logs, MemorySchedules(), lock=lock, lock_ttl_seconds=120)
    calls: list[str] = []

    async def callback(scheduled: ScheduleTask) -> dict[str, object]:
        calls.append(scheduled.id)
        return {"result_count": 1}

    service.register(task(), callback)
    await service.execute_task(task(), callback)
    await service.run_now("daily")

    assert calls == ["daily", "daily"]
    assert all(log.status == "success" for log in logs.logs.values())
    assert lock.releases == 2


@pytest.mark.asyncio
async def test_unavailable_lock_strict_mode_records_error_without_callback() -> None:
    """Strict mode rejects a Redis outage so duplicate delivery is not reintroduced."""
    logs = MemoryTaskLogs()
    service = SchedulerService(
        logs,
        MemorySchedules(),
        lock=UnavailableLock(),
        lock_ttl_seconds=120,
        lock_strict_mode=True,
    )
    calls = 0

    async def callback(_: ScheduleTask) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {}

    await service.execute_task(task(), callback)

    assert calls == 0
    assert next(iter(logs.logs.values())).status == "error"


@pytest.mark.asyncio
async def test_unavailable_lock_relaxed_mode_warns_and_runs() -> None:
    """Relaxed mode provides the explicit operational escape hatch."""
    logs = MemoryTaskLogs()
    service = SchedulerService(
        logs,
        MemorySchedules(),
        lock=UnavailableLock(),
        lock_ttl_seconds=120,
        lock_strict_mode=False,
    )
    calls = 0

    async def callback(_: ScheduleTask) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {}

    await service.execute_task(task(), callback)

    assert calls == 1
    assert next(iter(logs.logs.values())).status == "success"
