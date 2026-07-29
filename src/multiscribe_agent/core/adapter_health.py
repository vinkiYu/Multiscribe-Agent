"""Persisted health state and automatic disablement for source adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from multiscribe_agent.infra.db import Database

_MAX_ERROR_LENGTH = 200


@dataclass(frozen=True, slots=True)
class AdapterHealth:
    """Current operational state for one source adapter."""

    adapter_id: str
    consecutive_failures: int
    disabled: bool
    last_status: str
    last_error: str | None
    last_run_at: str | None
    updated_at: str
    just_disabled: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable health payload."""
        data = asdict(self)
        data.pop("just_disabled", None)
        return data


class AdapterHealthRepository:
    """Read and atomically update adapter health rows in SQLite."""

    def __init__(self, failure_threshold: int = 3) -> None:
        """Configure the number of consecutive failures that disables an adapter."""
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        self._failure_threshold = failure_threshold

    async def record_result(
        self,
        db: Database,
        *,
        adapter_id: str,
        success: bool,
        error: str | None = None,
    ) -> AdapterHealth:
        """Record one run, reset successes, and auto-disable at the configured threshold."""
        current = await self.get(db, adapter_id=adapter_id)
        now = datetime.now(UTC).isoformat()
        failures = 0 if success else (current.consecutive_failures if current else 0) + 1
        disabled = current.disabled if current else False
        just_disabled = not success and not disabled and failures >= self._failure_threshold
        if just_disabled:
            disabled = True
        status = "success" if success else "error"
        last_error = None if success else _truncate_error(error)
        await db.execute(
            """
            INSERT INTO adapter_health(
                adapter_id, consecutive_failures, disabled, last_status, last_error,
                last_run_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(adapter_id) DO UPDATE SET
                consecutive_failures = excluded.consecutive_failures,
                disabled = excluded.disabled,
                last_status = excluded.last_status,
                last_error = excluded.last_error,
                last_run_at = excluded.last_run_at,
                updated_at = excluded.updated_at
            """,
            (
                adapter_id,
                failures,
                int(disabled),
                status,
                last_error,
                now,
                now,
            ),
        )
        return AdapterHealth(
            adapter_id=adapter_id,
            consecutive_failures=failures,
            disabled=disabled,
            last_status=status,
            last_error=last_error,
            last_run_at=now,
            updated_at=now,
            just_disabled=just_disabled,
        )

    async def get(self, db: Database, *, adapter_id: str) -> AdapterHealth | None:
        """Return one adapter health row, or ``None`` when it has never run."""
        row = await db.fetchone("SELECT * FROM adapter_health WHERE adapter_id = ?", (adapter_id,))
        return self._from_row(row) if row is not None else None

    async def list_all(self, db: Database) -> list[AdapterHealth]:
        """Return all adapter health rows ordered by adapter ID."""
        rows = await db.fetchall("SELECT * FROM adapter_health ORDER BY adapter_id")
        return [self._from_row(row) for row in rows]

    async def set_disabled(self, db: Database, *, adapter_id: str, disabled: bool) -> None:
        """Manually enable or disable an adapter; enabling clears its failure streak."""
        current = await self.get(db, adapter_id=adapter_id)
        now = datetime.now(UTC).isoformat()
        failures = 0 if not disabled else (current.consecutive_failures if current else 0)
        status = current.last_status if current else "unknown"
        last_error = current.last_error if current and disabled else None
        await db.execute(
            """
            INSERT INTO adapter_health(
                adapter_id, consecutive_failures, disabled, last_status, last_error,
                last_run_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(adapter_id) DO UPDATE SET
                consecutive_failures = excluded.consecutive_failures,
                disabled = excluded.disabled,
                last_status = excluded.last_status,
                last_error = excluded.last_error,
                last_run_at = excluded.last_run_at,
                updated_at = excluded.updated_at
            """,
            (
                adapter_id,
                failures,
                int(disabled),
                status,
                last_error,
                current.last_run_at if current else None,
                now,
            ),
        )

    async def list_disabled(self, db: Database) -> set[str]:
        """Return adapter IDs currently marked as disabled."""
        rows = await db.fetchall(
            "SELECT adapter_id FROM adapter_health WHERE disabled = 1 ORDER BY adapter_id"
        )
        return {str(row["adapter_id"]) for row in rows}

    @staticmethod
    def _from_row(row: Mapping[str, Any]) -> AdapterHealth:
        """Convert a SQLite row into the typed health value object."""
        return AdapterHealth(
            adapter_id=str(row["adapter_id"]),
            consecutive_failures=int(row["consecutive_failures"]),
            disabled=bool(row["disabled"]),
            last_status=str(row["last_status"]),
            last_error=str(row["last_error"]) if row["last_error"] is not None else None,
            last_run_at=str(row["last_run_at"]) if row["last_run_at"] is not None else None,
            updated_at=str(row["updated_at"]),
        )


def _truncate_error(error: str | None) -> str:
    """Keep persisted adapter errors bounded for operational dashboards."""
    if not error:
        return "unknown adapter error"
    return error[:_MAX_ERROR_LENGTH]
