"""Persistent, redacted records of publisher delivery outcomes."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal, cast
from uuid import uuid4

import structlog

from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.dialect import ExplicitDatabaseDialectMixin

_MAX_PREVIEW_LENGTH = 200
_TABLE_NAME = "publish_history"
_MAX_QUERY_LIMIT = 200
_INSERT_RECORD = """
INSERT INTO publish_history (
    id, publisher_id, status, title, content_preview, result_data,
    error_message, published_at, adapter_name, digest_date, content_hash
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
_INSERT_IDEMPOTENT_RECORD = """
INSERT INTO publish_history (
    id, publisher_id, status, title, content_preview, result_data,
    error_message, published_at, adapter_name, digest_date, content_hash
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(publisher_id, digest_date) DO NOTHING
"""

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PublishRecord:
    """One persisted outcome from a publisher target."""

    id: str
    publisher_id: str
    status: Literal["success", "error"]
    title: str
    content_preview: str
    result_data: dict[str, object]
    error_message: str | None
    published_at: datetime
    adapter_name: str | None
    digest_date: str | None = None
    content_hash: str | None = None


class PublishHistory(ExplicitDatabaseDialectMixin):
    """Store and query publisher results through an injected application database."""

    @staticmethod
    def sanitize(content: str) -> str:
        """Redact common credential forms and return a bounded preview.

        Args:
            content: Rendered publish content or diagnostic text.

        Returns:
            A credential-free preview no longer than 200 characters.
        """
        patterns = (
            r"(?i)bearer[\s:]+[\w.-]+",
            r"sk-[\w-]{16,}",
            r"(?i)token[=:][^\s,;]{10,}",
            r"access_token=[^\s&]+",
            r"(?i)key=[^\s&]{16,}",
            r"https://oapi\.dingtalk\.com/robot/send[^\s]+",
            r"https://qyapi\.weixin\.qq\.com/cgi-bin/webhook/send[^\s]+",
            r"https://open\.feishu\.cn/open-apis/bot/v2/hook/[^\s&]+",
            r"(?i)app_[a-z0-9_]{16,}",
        )
        sanitized = content
        for pattern in patterns:
            sanitized = re.sub(pattern, "[REDACTED]", sanitized)
        return sanitized[:_MAX_PREVIEW_LENGTH]

    async def add(
        self,
        db: Database,
        publisher_id: str,
        status: Literal["success", "error"],
        title: str,
        content: str,
        result_data: dict[str, object],
        error_message: str | None = None,
        adapter_name: str | None = None,
        digest_date: str | None = None,
        content_hash: str | None = None,
    ) -> str:
        """Persist one normalized publisher outcome and return its generated identifier."""
        record_id = str(uuid4())
        _validate_digest_date(digest_date)
        published_at = datetime.now(UTC)
        statement = _INSERT_IDEMPOTENT_RECORD if digest_date is not None else _INSERT_RECORD
        await self._execute(
            db,
            statement,
            (
                record_id,
                publisher_id,
                status,
                title,
                self.sanitize(content),
                json.dumps(result_data, ensure_ascii=False, sort_keys=True),
                error_message,
                published_at.isoformat(),
                adapter_name,
                digest_date,
                content_hash,
            ),
        )
        if digest_date is not None:
            existing = await self._fetchone(
                db,
                "SELECT id FROM publish_history WHERE publisher_id = ? AND digest_date = ?",
                (publisher_id, digest_date),
            )
            if existing is not None:
                record_id = str(existing["id"])
        log.info("publish_history_added", publisher_id=publisher_id, record_id=record_id)
        return record_id

    async def query(
        self,
        db: Database,
        publisher_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
        digest_date: str | None = None,
    ) -> list[PublishRecord]:
        """Return newest records after applying optional publisher and time filters."""
        filters, parameters = _build_filters(
            publisher_id=publisher_id,
            from_date=from_date,
            to_date=to_date,
            digest_date=digest_date,
        )
        where_clause = " AND ".join(filters) if filters else "1 = 1"
        parameters.append(max(1, min(limit, _MAX_QUERY_LIMIT)))
        parameters.append(max(0, offset))
        # where_clause consists only of static clauses defined above; all values use placeholders.
        statement = f"""
            SELECT id, publisher_id, status, title, content_preview, result_data,
                   error_message, published_at, adapter_name, digest_date, content_hash
            FROM {_TABLE_NAME}
            WHERE {where_clause}
            ORDER BY published_at DESC, id DESC
            LIMIT ?
            OFFSET ?
            """  # noqa: S608
        rows = await self._fetchall(
            db,
            statement,
            parameters,
        )
        return [_record_from_row(row) for row in rows]

    async def count(
        self,
        db: Database,
        publisher_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        digest_date: str | None = None,
    ) -> int:
        """Return the number of records matching the given filters."""
        filters, parameters = _build_filters(
            publisher_id=publisher_id,
            from_date=from_date,
            to_date=to_date,
            digest_date=digest_date,
        )
        where_clause = " AND ".join(filters) if filters else "1 = 1"
        row = await self._fetchone(
            db,
            f"SELECT COUNT(*) AS count FROM {_TABLE_NAME} WHERE {where_clause}",  # noqa: S608
            parameters,
        )
        return int(row["count"]) if row is not None else 0

    async def summary(
        self,
        db: Database,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> dict[str, object]:
        """Return total, successful, and failed deliveries for an optional window."""
        filters: list[str] = []
        parameters: list[object] = []
        if from_date is not None:
            filters.append("published_at >= ?")
            parameters.append(from_date.isoformat())
        if to_date is not None:
            filters.append("published_at <= ?")
            parameters.append(to_date.isoformat())
        where_clause = " AND ".join(filters) if filters else "1 = 1"
        rows = await self._fetchall(
            db,
            (
                f"SELECT status, COUNT(*) AS count FROM {_TABLE_NAME} "  # noqa: S608
                f"WHERE {where_clause} GROUP BY status"
            ),
            parameters,
        )
        counts = {"success": 0, "error": 0}
        for row in rows:
            status = str(row["status"])
            if status in counts:
                counts[status] = int(row["count"])
        return {"total": counts["success"] + counts["error"], **counts}

    async def recent_content_hashes(self, db: Database, since_date: str) -> set[str]:
        """Return successful digest fingerprints retained in publish history."""
        _validate_digest_date(since_date)
        rows = await self._fetchall(
            db,
            """
            SELECT content_hash
            FROM publish_history
            WHERE status = 'success'
              AND digest_date >= ?
              AND content_hash IS NOT NULL
              AND content_hash != ''
            """,
            (since_date,),
        )
        hashes: set[str] = set()
        for row in rows:
            value = row.get("content_hash")
            if not isinstance(value, str) or not value:
                continue
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                hashes.add(value)
                continue
            if isinstance(decoded, list):
                hashes.update(item for item in decoded if isinstance(item, str) and item)
            else:
                hashes.add(value)
        return hashes


def _record_from_row(row: Mapping[str, Any]) -> PublishRecord:
    """Convert a trusted SQLite row into a typed published-record value."""
    status = str(row["status"])
    if status not in {"success", "error"}:
        raise ValueError("publish history contains an invalid status")
    result_data = json.loads(str(row["result_data"]))
    if not isinstance(result_data, dict):
        raise ValueError("publish history contains non-object result data")
    return PublishRecord(
        id=str(row["id"]),
        publisher_id=str(row["publisher_id"]),
        status=cast(Literal["success", "error"], status),
        title=str(row["title"]),
        content_preview=str(row["content_preview"]),
        result_data=result_data,
        error_message=_optional_row_text(row["error_message"]),
        published_at=datetime.fromisoformat(str(row["published_at"])),
        adapter_name=_optional_row_text(row["adapter_name"]),
        digest_date=_optional_row_text(row.get("digest_date")),
        content_hash=_optional_row_text(row.get("content_hash")),
    )


def _build_filters(
    *,
    publisher_id: str | None,
    from_date: datetime | None,
    to_date: datetime | None,
    digest_date: str | None,
) -> tuple[list[str], list[object]]:
    """Build the shared publish-history predicates and bind values."""
    filters: list[str] = []
    parameters: list[object] = []
    if publisher_id is not None:
        filters.append("publisher_id = ?")
        parameters.append(publisher_id)
    if from_date is not None:
        filters.append("published_at >= ?")
        parameters.append(from_date.isoformat())
    if to_date is not None:
        filters.append("published_at <= ?")
        parameters.append(to_date.isoformat())
    if digest_date is not None:
        _validate_digest_date(digest_date)
        filters.append("digest_date = ?")
        parameters.append(digest_date)
    return filters, parameters


def _validate_digest_date(value: str | None) -> None:
    """Validate the optional daily idempotency key format."""
    if value is None:
        return
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        raise ValueError("digest_date must use YYYY-MM-DD format")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("digest_date must be a valid calendar date") from exc


def _optional_row_text(value: object) -> str | None:
    """Normalize nullable SQLite text columns for the typed record boundary."""
    return str(value) if value is not None else None


_history: PublishHistory | None = None


def get_publish_history() -> PublishHistory:
    """Return the process-local stateless publish-history service."""
    global _history
    if _history is None:
        _history = PublishHistory()
    return _history
