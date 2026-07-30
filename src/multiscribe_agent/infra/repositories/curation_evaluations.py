"""Persistence for per-run daily-digest curation evaluation outcomes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.dialect import DialectRepositoryMixin, PgDialect, UpsertStyle

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS curation_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_run_id TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    recorded_at INTEGER NOT NULL,
    rounds INTEGER NOT NULL DEFAULT 0,
    converged INTEGER NOT NULL DEFAULT 0,
    exit_reason TEXT NOT NULL DEFAULT 'max_rounds',
    final_score REAL,
    score_delta REAL,
    avg_iter_score REAL,
    result_count INTEGER NOT NULL DEFAULT 0,
    usage_json TEXT NOT NULL DEFAULT '{}'
)
"""
_CREATE_DATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_curation_evaluations_date
ON curation_evaluations(date DESC, id DESC)
"""
_CREATE_TABLE_POSTGRES = _CREATE_TABLE.replace(
    "id INTEGER PRIMARY KEY AUTOINCREMENT", "id BIGSERIAL PRIMARY KEY"
)


@dataclass(frozen=True, slots=True)
class CurationEvaluationRecord:
    """One daily-digest curation loop's durable evaluation summary."""

    workflow_run_id: str
    date: str
    recorded_at: int
    rounds: int
    converged: bool
    exit_reason: str
    final_score: float | None
    score_delta: float | None
    avg_iter_score: float | None
    result_count: int
    usage: dict[str, int]


class CurationEvaluationRepository(DialectRepositoryMixin):
    """Persist and query curation loop outcomes through the application database."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._schema_ready = False

    async def ensure_schema(self) -> None:
        """Create the bounded evaluation schema for existing SQLite databases."""
        if not self._schema_ready:
            await self._execute(
                _CREATE_TABLE_POSTGRES if isinstance(self._dialect, PgDialect) else _CREATE_TABLE
            )
            await self._execute(_CREATE_DATE_INDEX)
            self._schema_ready = True

    async def upsert(self, evaluation: CurationEvaluationRecord) -> None:
        """Insert or replace one evaluation using the workflow run as its idempotency key."""
        await self.ensure_schema()
        columns = (
            "workflow_run_id",
            "date",
            "recorded_at",
            "rounds",
            "converged",
            "exit_reason",
            "final_score",
            "score_delta",
            "avg_iter_score",
            "result_count",
            "usage_json",
        )
        sql = self._upsert_sql(
            table="curation_evaluations",
            columns=columns,
            style=UpsertStyle.ON_CONFLICT_DO_UPDATE,
            conflict_target=("workflow_run_id",),
            update_columns=columns[1:],
        )
        await self._execute(
            sql,
            (
                evaluation.workflow_run_id,
                evaluation.date,
                evaluation.recorded_at,
                evaluation.rounds,
                int(evaluation.converged),
                evaluation.exit_reason,
                evaluation.final_score,
                evaluation.score_delta,
                evaluation.avg_iter_score,
                evaluation.result_count,
                json.dumps(evaluation.usage, sort_keys=True),
            ),
        )

    async def query(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 50,
    ) -> list[CurationEvaluationRecord]:
        """Return newest evaluation rows, filtered by an inclusive date interval."""
        await self.ensure_schema()
        filters, parameters = _date_filters(from_date, to_date)
        parameters.append(max(1, min(limit, 200)))
        where_clause = " AND ".join(filters) if filters else "1 = 1"
        rows = await self._fetchall(
            f"""
            SELECT workflow_run_id, date, recorded_at, rounds, converged, exit_reason,
                   final_score, score_delta, avg_iter_score, result_count, usage_json
            FROM curation_evaluations
            WHERE {where_clause}
            ORDER BY recorded_at DESC, id DESC
            LIMIT ?
            """,  # noqa: S608
            parameters,
        )
        return [_record_from_row(row) for row in rows]

    async def summary(
        self, from_date: str | None = None, to_date: str | None = None
    ) -> dict[str, object]:
        """Return quality, convergence, and exit-reason aggregates for a date interval."""
        await self.ensure_schema()
        filters, parameters = _date_filters(from_date, to_date)
        where_clause = " AND ".join(filters) if filters else "1 = 1"
        totals = await self._fetchone(
            f"""
            SELECT COUNT(*) AS total_runs, SUM(converged) AS converged_runs,
                   AVG(final_score) AS avg_final_score, AVG(rounds) AS avg_rounds
            FROM curation_evaluations
            WHERE {where_clause}
            """,  # noqa: S608
            parameters,
        )
        reason_rows = await self._fetchall(
            f"""
            SELECT exit_reason, COUNT(*) AS count
            FROM curation_evaluations
            WHERE {where_clause}
            GROUP BY exit_reason
            """,  # noqa: S608
            parameters,
        )
        total_runs = int(totals["total_runs"]) if totals is not None else 0
        converged_runs = int(totals["converged_runs"] or 0) if totals is not None else 0
        avg_score = _optional_float(totals["avg_final_score"]) if totals else None
        avg_rounds = _optional_float(totals["avg_rounds"]) if totals else 0.0
        return {
            "total_runs": total_runs,
            "converged_runs": converged_runs,
            "avg_score": avg_score,
            "avg_final_score": avg_score,
            "avg_rounds": avg_rounds,
            "converge_rate": (converged_runs / total_runs * 100) if total_runs else 0.0,
            "per_reason_counts": {
                str(row["exit_reason"]): _row_int(row["count"]) for row in reason_rows
            },
        }


def _date_filters(from_date: str | None, to_date: str | None) -> tuple[list[str], list[object]]:
    """Build parameterized inclusive date filters from public query inputs."""
    filters: list[str] = []
    parameters: list[object] = []
    if from_date is not None:
        filters.append("date >= ?")
        parameters.append(from_date)
    if to_date is not None:
        filters.append("date <= ?")
        parameters.append(to_date)
    return filters, parameters


def _record_from_row(row: Mapping[str, object]) -> CurationEvaluationRecord:
    """Convert a trusted SQLite row to its typed API-facing representation."""
    usage = json.loads(str(row["usage_json"]))
    if not isinstance(usage, dict):
        raise ValueError("curation evaluation usage must be an object")
    return CurationEvaluationRecord(
        workflow_run_id=str(row["workflow_run_id"]),
        date=str(row["date"]),
        recorded_at=_row_int(row["recorded_at"]),
        rounds=_row_int(row["rounds"]),
        converged=bool(row["converged"]),
        exit_reason=str(row["exit_reason"]),
        final_score=_optional_float(row["final_score"]),
        score_delta=_optional_float(row["score_delta"]),
        avg_iter_score=_optional_float(row["avg_iter_score"]),
        result_count=_row_int(row["result_count"]),
        usage={key: _as_int(value) for key, value in usage.items()},
    )


def _optional_float(value: object) -> float | None:
    """Normalize nullable database numeric values."""
    if not isinstance(value, int | float | str) or isinstance(value, bool):
        return None
    return float(value)


def _row_int(value: object) -> int:
    """Normalize SQLite integer values at the typed repository boundary."""
    return int(value) if isinstance(value, int | float | str) and not isinstance(value, bool) else 0


def _as_int(value: object) -> int:
    """Preserve numeric usage counters while rejecting malformed JSON values."""
    return int(value) if isinstance(value, int | float | str) and not isinstance(value, bool) else 0
