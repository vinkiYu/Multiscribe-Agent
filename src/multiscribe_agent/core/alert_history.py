"""Durable alert history records used by operations and audit views."""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass

from multiscribe_agent.infra.db_protocol import DatabaseProtocol
from multiscribe_agent.infra.dialect import DialectRepositoryMixin

_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


@dataclass(frozen=True, slots=True)
class AlertRecord:
    """One persisted alert event and its acknowledgement state."""

    id: str
    rule_name: str
    metric: str
    threshold: float
    value: float
    description: str
    fired_at: int
    acknowledged: bool
    acknowledged_by: str | None
    acknowledged_at: int | None
    metadata: dict[str, object]


class AlertHistoryRepository(DialectRepositoryMixin):
    """Persist, query, and acknowledge alert events."""

    def __init__(self, db: DatabaseProtocol) -> None:
        self._db = db

    async def record(
        self,
        *,
        rule_name: str,
        metric: str,
        threshold: float,
        value: float,
        description: str,
        fired_at: int,
        metadata: dict[str, object] | None = None,
    ) -> str:
        """Insert one alert event and return its unique identifier."""
        record_id = _new_ulid()
        await self._execute(
            """
            INSERT INTO alert_history
                (id, rule_name, metric, threshold, value, description,
                 fired_at, acknowledged, acknowledged_by, acknowledged_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, ?)
            """,
            (
                record_id,
                rule_name,
                metric,
                threshold,
                value,
                description,
                fired_at,
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
            ),
        )
        return record_id

    async def query_recent(
        self, limit: int = 50, acknowledged: bool | None = None
    ) -> list[AlertRecord]:
        """Return newest alerts, optionally filtered by acknowledgement state."""
        bounded_limit = max(1, min(limit, 200))
        filters: list[str] = []
        parameters: list[object] = []
        if acknowledged is not None:
            filters.append("acknowledged = ?")
            parameters.append(int(acknowledged))
        where_clause = " AND ".join(filters) if filters else "1 = 1"
        parameters.append(bounded_limit)
        rows = await self._fetchall(
            f"""
            SELECT id, rule_name, metric, threshold, value, description,
                   fired_at, acknowledged, acknowledged_by, acknowledged_at, metadata
            FROM alert_history
            WHERE {where_clause}
            ORDER BY fired_at DESC, id DESC
            LIMIT ?
            """,  # noqa: S608 - filter is built from a fixed clause
            parameters,
        )
        return [_row_to_alert_record(row) for row in rows]

    async def acknowledge(self, id_: str, by: str) -> None:
        """Mark an alert as acknowledged by an operator."""
        await self._execute(
            """
            UPDATE alert_history
            SET acknowledged = 1, acknowledged_by = ?, acknowledged_at = ?
            WHERE id = ?
            """,
            (by, int(time.time()), id_),
        )


def _row_to_alert_record(row: Mapping[str, object]) -> AlertRecord:
    """Convert one database mapping into the typed alert record."""
    raw_metadata = row.get("metadata")
    try:
        parsed_metadata = json.loads(str(raw_metadata)) if raw_metadata else {}
    except (TypeError, ValueError):
        parsed_metadata = {}
    metadata = parsed_metadata if isinstance(parsed_metadata, dict) else {}
    acknowledged_by = row.get("acknowledged_by")
    raw_acknowledged_at = row.get("acknowledged_at")
    return AlertRecord(
        id=str(row["id"]),
        rule_name=str(row["rule_name"]),
        metric=str(row["metric"]),
        threshold=float(str(row["threshold"])),
        value=float(str(row["value"])),
        description=str(row["description"]),
        fired_at=int(str(row["fired_at"])),
        acknowledged=bool(row["acknowledged"]),
        acknowledged_by=str(acknowledged_by) if acknowledged_by else None,
        acknowledged_at=int(str(raw_acknowledged_at)) if raw_acknowledged_at else None,
        metadata=metadata,
    )


def _new_ulid() -> str:
    """Create a sortable 26-character ULID without adding a runtime dependency."""
    value = (int(time.time() * 1000) << 80) | int.from_bytes(secrets.token_bytes(10), "big")
    chars: list[str] = []
    for _ in range(26):
        value, remainder = divmod(value, 32)
        chars.append(_ULID_ALPHABET[remainder])
    return "".join(reversed(chars))
