"""Per-model token usage aggregated by calendar day."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.dialect import DialectRepositoryMixin, PgDialect, UpsertStyle

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS daily_usage_by_model (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    model_name TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    llm_calls INTEGER NOT NULL DEFAULT 0,
    UNIQUE(date, model_name)
)
"""
_CREATE_TABLE_POSTGRES = _CREATE_TABLE.replace(
    "id INTEGER PRIMARY KEY AUTOINCREMENT", "id BIGSERIAL PRIMARY KEY"
)


@dataclass(frozen=True, slots=True)
class DailyUsageByModelRecord:
    """One calendar day's aggregated usage for one provider model."""

    date: str
    model_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    llm_calls: int


class DailyUsageByModelRepository(DialectRepositoryMixin):
    """Persist per-model usage without changing the existing daily aggregate table."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._schema_ready = False

    async def ensure_schema(self) -> None:
        """Create the table lazily so existing databases need no migration."""
        if not self._schema_ready:
            await self._execute(
                _CREATE_TABLE_POSTGRES if isinstance(self._dialect, PgDialect) else _CREATE_TABLE
            )
            self._schema_ready = True

    async def upsert(self, date: str, by_model: Mapping[str, Mapping[str, object]]) -> None:
        """Increment model buckets for one date from a serialized digest usage payload."""
        await self.ensure_schema()
        for raw_model_name, bucket in by_model.items():
            model_name = raw_model_name.strip() or "unknown"
            values = (
                _non_negative_int(bucket.get("input_tokens")),
                _non_negative_int(bucket.get("output_tokens")),
                _non_negative_int(bucket.get("total_tokens")),
                _non_negative_int(bucket.get("llm_calls")),
            )
            await self._execute(
                self._upsert_sql(
                    table="daily_usage_by_model",
                    columns=(
                        "date",
                        "model_name",
                        "input_tokens",
                        "output_tokens",
                        "total_tokens",
                        "llm_calls",
                    ),
                    style=UpsertStyle.ON_CONFLICT_DO_UPDATE,
                    conflict_target=("date", "model_name"),
                    update_columns=("input_tokens", "output_tokens", "total_tokens", "llm_calls"),
                    update_expressions={
                        "input_tokens": "input_tokens + excluded.input_tokens",
                        "output_tokens": "output_tokens + excluded.output_tokens",
                        "total_tokens": "total_tokens + excluded.total_tokens",
                        "llm_calls": "llm_calls + excluded.llm_calls",
                    },
                ),
                (date, model_name, *values),
            )

    async def query(self, from_date: str, to_date: str) -> list[DailyUsageByModelRecord]:
        """Return model aggregates in an inclusive date range, newest usage first."""
        await self.ensure_schema()
        rows = await self._fetchall(
            """
            SELECT date, model_name, input_tokens, output_tokens, total_tokens, llm_calls
            FROM daily_usage_by_model
            WHERE date >= ? AND date <= ?
            ORDER BY date DESC, total_tokens DESC, model_name ASC
            """,
            (from_date, to_date),
        )
        return [
            DailyUsageByModelRecord(
                date=str(row["date"]),
                model_name=str(row["model_name"]),
                input_tokens=int(row["input_tokens"]),
                output_tokens=int(row["output_tokens"]),
                total_tokens=int(row["total_tokens"]),
                llm_calls=int(row["llm_calls"]),
            )
            for row in rows
        ]


def _non_negative_int(value: object) -> int:
    """Normalize dynamic usage payload values without failing analytics writes."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return 0
    try:
        return max(0, int(value))
    except (OverflowError, ValueError):
        return 0
