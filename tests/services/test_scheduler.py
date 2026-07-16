"""Tests for APScheduler orchestration and task-log lifecycle handling."""

from __future__ import annotations

import pytest

from multiscribe_agent.domain.models import ScheduleTask, TaskLog
from multiscribe_agent.services.scheduler import SchedulerService, TaskExecutorRegistry


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
