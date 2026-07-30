"""Read-only daily curation quality aggregates for the operations console."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.dialect import DialectRepositoryMixin


@dataclass(frozen=True, slots=True)
class DailyCurationStat:
    """One persisted curation evaluation joined with its daily archive metrics."""

    date: str
    final_score: float | None
    result_count: int | None
    total_scanned: int | None
    efficiency: float | None
    converged: bool
    exit_reason: str
    rounds: int


class CurationStatsRepository(DialectRepositoryMixin):
    """Aggregate existing evaluation and archive rows without changing their schemas."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_by_period(self, from_date: str, to_date: str) -> list[DailyCurationStat]:
        """Return curation evaluations joined to the archive for an inclusive date range."""
        rows = await self._fetchall(
            """
            SELECT
                ce.date AS date,
                ce.final_score AS final_score,
                ce.result_count AS result_count,
                dda.total_scanned AS total_scanned,
                ce.converged AS converged,
                ce.exit_reason AS exit_reason,
                ce.rounds AS rounds
            FROM curation_evaluations ce
            LEFT JOIN daily_digest_archives dda
                ON dda.digest_date = ce.date
            WHERE ce.date BETWEEN ? AND ?
            ORDER BY ce.date ASC, ce.recorded_at ASC, ce.id ASC
            """,
            (from_date, to_date),
        )
        return [_stat_from_row(row) for row in rows]


def _stat_from_row(row: Mapping[str, object]) -> DailyCurationStat:
    """Normalize backend row values and calculate a bounded selection efficiency."""
    result_count = _optional_int(row.get("result_count"))
    total_scanned = _optional_int(row.get("total_scanned"))
    efficiency = (
        result_count / total_scanned
        if result_count is not None and total_scanned is not None and total_scanned > 0
        else None
    )
    return DailyCurationStat(
        date=str(row.get("date", "")),
        final_score=_optional_float(row.get("final_score")),
        result_count=result_count,
        total_scanned=total_scanned,
        efficiency=efficiency,
        converged=bool(row.get("converged")),
        exit_reason=str(row.get("exit_reason", "")),
        rounds=_optional_int(row.get("rounds")) or 0,
    )


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
