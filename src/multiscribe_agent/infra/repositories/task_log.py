"""SQLite repository for task lifecycle records."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from multiscribe_agent.domain.models import TaskLog
from multiscribe_agent.infra.db_protocol import DatabaseProtocol
from multiscribe_agent.infra.dialect import DialectRepositoryMixin

_UPDATE_FIELDS = frozenset(
    {
        "task_name",
        "start_time",
        "end_time",
        "duration_ms",
        "status",
        "progress",
        "message",
        "result_count",
    }
)


class TaskLogRepository(DialectRepositoryMixin):
    """Create, update, and retrieve task lifecycle records."""

    def __init__(self, db: DatabaseProtocol) -> None:
        """Create a repository using an initialized database."""
        self._db = db

    async def create(self, log: TaskLog) -> str:
        """Insert a task log and return its generated identifier."""
        row_id = await self._execute(
            """
            INSERT INTO task_logs(
                task_id, task_name, start_time, end_time, duration, status,
                progress, message, result_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                log.task_id,
                log.task_name,
                log.start_time,
                log.end_time,
                log.duration_ms,
                log.status,
                log.progress,
                log.message,
                log.result_count,
            ),
        )
        if row_id is None:
            raise RuntimeError("INSERT INTO task_logs did not return an id")
        return str(row_id)

    async def update(self, log_id: str, **fields: object) -> None:
        """Update only whitelisted columns on an existing task log."""
        for field in fields:
            if field not in _UPDATE_FIELDS:
                raise ValueError(f"unsupported task log field: {field}")
        if not fields:
            return

        current = await self.get(log_id)
        if current is None:
            return
        updated = current.model_copy(update=fields)
        await self._execute(
            """
            UPDATE task_logs SET
                task_name = ?, start_time = ?, end_time = ?, duration = ?, status = ?,
                progress = ?, message = ?, result_count = ?
            WHERE id = ?
            """,
            (
                updated.task_name,
                updated.start_time,
                updated.end_time,
                updated.duration_ms,
                updated.status,
                updated.progress,
                updated.message,
                updated.result_count,
                log_id,
            ),
        )

    async def get(self, log_id: str) -> TaskLog | None:
        """Return a task log by identifier."""
        row = await self._fetchone("SELECT * FROM task_logs WHERE id = ?", (log_id,))
        if row is None:
            return None
        return self._to_task_log(row)

    @staticmethod
    def _to_task_log(row: Mapping[str, Any]) -> TaskLog:
        """Convert a task_logs row into a validated TaskLog model."""
        data = dict(row)
        data["id"] = str(data["id"])
        data["duration_ms"] = data.pop("duration")
        return TaskLog.model_validate(cast(dict[str, object], data))
