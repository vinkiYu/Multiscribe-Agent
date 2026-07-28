"""Cron scheduler service with injected task executors and task-log lifecycle tracking."""

# APScheduler 3.x does not provide type information.
# mypy: disable-error-code=import-untyped

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Literal

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from multiscribe_agent.domain.models import ScheduleTask, TaskLog
from multiscribe_agent.domain.ports import EntityJsonRepository, TaskLogRepository
from multiscribe_agent.services.scheduler_lock import (
    AcquireResult,
    NoOpSchedulerLock,
    SchedulerLock,
)

TaskCallback = Callable[[ScheduleTask], Awaitable[dict[str, object]]]
log = structlog.get_logger(__name__)


class TaskExecutorRegistry:
    """Map schedule task types to asynchronously injected execution callbacks."""

    def __init__(self) -> None:
        """Create an empty executor registry."""
        self._callbacks: dict[str, TaskCallback] = {}

    def register(self, task_type: str, callback: TaskCallback) -> None:
        """Register or replace the callback for one task type."""
        self._callbacks[task_type] = callback

    def get(self, task_type: str) -> TaskCallback | None:
        """Return the callback registered for one task type."""
        return self._callbacks.get(task_type)


class SchedulerService:
    """Load persisted cron schedules and execute their injected callbacks safely."""

    def __init__(
        self,
        task_log_repo: TaskLogRepository,
        schedule_store: EntityJsonRepository,
        timezone: str = "Asia/Shanghai",
        executor_registry: TaskExecutorRegistry | None = None,
        lock: SchedulerLock | None = None,
        lock_ttl_seconds: int = 7_200,
        lock_strict_mode: bool = True,
    ) -> None:
        """Create a scheduler backed by task logs and persisted schedule data."""
        self._task_log_repo = task_log_repo
        self._schedule_store = schedule_store
        self._timezone = timezone
        self._scheduler = AsyncIOScheduler(timezone=timezone)
        self._registry = executor_registry or TaskExecutorRegistry()
        self._lock = lock or NoOpSchedulerLock()
        self._lock_ttl_seconds = lock_ttl_seconds
        self._lock_strict_mode = lock_strict_mode
        self._tasks: dict[str, ScheduleTask] = {}

    async def start(self) -> None:
        """Load enabled stored tasks, register them, and start the async scheduler."""
        for data in await self._schedule_store.list_all("schedules"):
            task = ScheduleTask.model_validate(data)
            self._tasks[task.id] = task
            if task.enabled:
                callback = self._registry.get(task.task_type)
                if callback is not None:
                    self.register(task, callback)
        if not self._scheduler.running:
            self._scheduler.start()

    async def stop(self) -> None:
        """Stop scheduled jobs and release scheduler runtime state."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._tasks.clear()

    def register(self, task: ScheduleTask, callback: TaskCallback) -> None:
        """Register a task callback and cron job after validating its expression."""
        trigger = CronTrigger.from_crontab(task.cron, timezone=self._timezone)
        self._registry.register(task.task_type, callback)
        self._tasks[task.id] = task
        self._scheduler.add_job(
            self.execute_task,
            trigger=trigger,
            args=[task, callback],
            id=task.id,
            replace_existing=True,
        )

    def unregister(self, task_id: str) -> None:
        """Remove one registered task and cancel its future cron triggers."""
        if self._scheduler.get_job(task_id) is not None:
            self._scheduler.remove_job(task_id)
        self._tasks.pop(task_id, None)

    async def reload(self) -> None:
        """Reload persisted enabled schedules without changing executor registrations."""
        was_running = self._scheduler.running
        if was_running:
            self._scheduler.pause()
        self._scheduler.remove_all_jobs()
        self._tasks.clear()
        for data in await self._schedule_store.list_all("schedules"):
            task = ScheduleTask.model_validate(data)
            self._tasks[task.id] = task
            callback = self._registry.get(task.task_type)
            if task.enabled and callback is not None:
                self.register(task, callback)
        if was_running:
            self._scheduler.resume()

    async def run_now(self, task_id: str) -> None:
        """Run one registered task immediately without waiting for its cron trigger."""
        task = self._tasks.get(task_id)
        if task is None:
            raise ValueError(f"unknown scheduled task: {task_id}")
        await self.execute_task(task, self._registry.get(task.task_type))

    async def execute_task(self, task: ScheduleTask, callback: TaskCallback | None) -> None:
        """Run one callback once per task and UTC calendar day under a distributed lease."""
        run_date = datetime.now(UTC).strftime("%Y-%m-%d")
        lock_key = f"multiscribe:scheduler:lock:{task.id}:{run_date}"
        lock_result = await self._try_acquire(lock_key)
        if not lock_result.acquired and not lock_result.allow_without_lock:
            status: Literal["error", "skipped"] = "error" if lock_result.unavailable else "skipped"
            await self._record_lock_outcome(task, status, lock_result.reason)
            if status == "skipped":
                log.info(
                    "scheduler_task_skipped",
                    task_id=task.id,
                    run_date=run_date,
                    reason=lock_result.reason,
                )
            else:
                log.error(
                    "scheduler_task_lock_rejected",
                    task_id=task.id,
                    run_date=run_date,
                    reason=lock_result.reason,
                )
            return

        started_at = datetime.now(UTC).isoformat()
        started = perf_counter()
        try:
            log_id = await self._task_log_repo.create(
                TaskLog(
                    task_id=task.id,
                    task_name=task.name,
                    start_time=started_at,
                    status="running",
                )
            )
            try:
                if callback is None:
                    raise LookupError(f"no executor registered for task type: {task.task_type}")
                result = await callback(task)
            except Exception as exc:
                log.warning("scheduled_task_failed", task_id=task.id, error_type=type(exc).__name__)
                await self._task_log_repo.update(
                    log_id,
                    status="error",
                    end_time=datetime.now(UTC).isoformat(),
                    duration_ms=self._duration_ms(started),
                    result_count=0,
                    message=str(exc),
                )
                return
            await self._task_log_repo.update(
                log_id,
                status="success",
                end_time=datetime.now(UTC).isoformat(),
                duration_ms=self._duration_ms(started),
                result_count=self._result_count(result),
                message=self._message(result),
            )
        finally:
            if lock_result.acquired and lock_result.token is not None:
                await self._lock.release(lock_key, lock_result.token)

    async def _try_acquire(self, lock_key: str) -> AcquireResult:
        """Acquire a lock and normalize connection failures into lock outcomes."""
        try:
            return await self._lock.acquire(lock_key, self._lock_ttl_seconds)
        except (ConnectionError, OSError, TimeoutError) as exc:
            log.warning(
                "scheduler_lock_unavailable",
                error_type=type(exc).__name__,
                strict_mode=self._lock_strict_mode,
            )
            return AcquireResult(
                acquired=False,
                reason="redis_unreachable",
                unavailable=True,
                allow_without_lock=not self._lock_strict_mode,
            )

    async def _record_lock_outcome(
        self, task: ScheduleTask, status: Literal["error", "skipped"], reason: str
    ) -> None:
        """Persist a terminal lock decision without creating a running log."""
        now = datetime.now(UTC).isoformat()
        await self._task_log_repo.create(
            TaskLog(
                task_id=task.id,
                task_name=task.name,
                start_time=now,
                end_time=now,
                duration_ms=0,
                status=status,
                result_count=0,
                message=f"scheduler lock: {reason}",
            )
        )

    @staticmethod
    def _duration_ms(started: float) -> int:
        """Return elapsed milliseconds rounded for task-log storage."""
        return round((perf_counter() - started) * 1000)

    @staticmethod
    def _result_count(result: dict[str, object]) -> int:
        """Extract a non-negative result count from a callback result mapping."""
        value = result.get("result_count", 0)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    @staticmethod
    def _message(result: dict[str, object]) -> str | None:
        """Extract an optional callback message from a callback result mapping."""
        value = result.get("message")
        return value if isinstance(value, str) else None
