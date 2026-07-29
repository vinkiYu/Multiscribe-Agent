"""Daily aggregate token usage persisted independently from task logs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.dialect import DialectRepositoryMixin, PgDialect

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS daily_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    llm_calls INTEGER NOT NULL DEFAULT 0,
    task_count INTEGER NOT NULL DEFAULT 0,
    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
_CREATE_TABLE_POSTGRES = _CREATE_TABLE.replace(
    "id INTEGER PRIMARY KEY AUTOINCREMENT", "id BIGSERIAL PRIMARY KEY"
)


@dataclass(frozen=True, slots=True)
class DailyUsageRecord:
    """One calendar day's aggregated model usage."""

    date: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    llm_calls: int
    task_count: int


class DailyUsageRepository(DialectRepositoryMixin):
    """Upsert and query scheduler usage without changing the core DB migration."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._schema_ready = False

    async def ensure_schema(self) -> None:
        """Create the table lazily and safely for old databases."""
        if not self._schema_ready:
            await self._execute(
                _CREATE_TABLE_POSTGRES if isinstance(self._dialect, PgDialect) else _CREATE_TABLE
            )
            self._schema_ready = True

    async def upsert(self, date: str, usage: Mapping[str, object]) -> None:
        """Increment the aggregate for ``date`` from a validated usage mapping."""
        await self.ensure_schema()
        values = tuple(
            _non_negative_int(usage.get(name))
            for name in ("input_tokens", "output_tokens", "total_tokens", "llm_calls")
        )
        await self._execute(
            """
            INSERT INTO daily_usage
                (date, input_tokens, output_tokens, total_tokens, llm_calls, task_count)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(date) DO UPDATE SET
                input_tokens = input_tokens + excluded.input_tokens,
                output_tokens = output_tokens + excluded.output_tokens,
                total_tokens = total_tokens + excluded.total_tokens,
                llm_calls = llm_calls + excluded.llm_calls,
                task_count = task_count + 1,
                recorded_at = CURRENT_TIMESTAMP
            """,
            (date, *values),
        )

    async def query(self, from_date: str, to_date: str) -> list[DailyUsageRecord]:
        """Return daily aggregates in the inclusive date range, newest first."""
        await self.ensure_schema()
        rows = await self._fetchall(
            """
            SELECT date, input_tokens, output_tokens, total_tokens, llm_calls, task_count
            FROM daily_usage
            WHERE date >= ? AND date <= ?
            ORDER BY date DESC
            """,
            (from_date, to_date),
        )
        return [
            DailyUsageRecord(
                date=str(row["date"]),
                input_tokens=int(row["input_tokens"]),
                output_tokens=int(row["output_tokens"]),
                total_tokens=int(row["total_tokens"]),
                llm_calls=int(row["llm_calls"]),
                task_count=int(row["task_count"]),
            )
            for row in rows
        ]


def _non_negative_int(value: object) -> int:
    """Normalize provider usage values while keeping analytics writes non-fatal."""
    if isinstance(value, bool):
        return 0
    if not isinstance(value, (int, float, str)):
        return 0
    try:
        return max(0, int(value))
    except (OverflowError, ValueError):
        return 0
