"""Persistent, redacted records of publisher delivery outcomes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import uuid4

import aiosqlite
import structlog

from multiscribe_agent.infra.db import Database

_MAX_PREVIEW_LENGTH = 200
_TABLE_NAME = "publish_history"
_MAX_QUERY_LIMIT = 200
_INSERT_RECORD = """
INSERT INTO publish_history (
    id, publisher_id, status, title, content_preview, result_data,
    error_message, published_at, adapter_name
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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


class PublishHistory:
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
    ) -> str:
        """Persist one normalized publisher outcome and return its generated identifier."""
        record_id = str(uuid4())
        published_at = datetime.now(UTC)
        await db.execute(
            _INSERT_RECORD,
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
            ),
        )
        log.info("publish_history_added", publisher_id=publisher_id, record_id=record_id)
        return record_id

    async def query(
        self,
        db: Database,
        publisher_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 50,
    ) -> list[PublishRecord]:
        """Return newest records after applying optional publisher and time filters."""
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
        where_clause = " AND ".join(filters) if filters else "1 = 1"
        parameters.append(max(1, min(limit, _MAX_QUERY_LIMIT)))
        # where_clause consists only of static clauses defined above; all values use placeholders.
        statement = f"""
            SELECT id, publisher_id, status, title, content_preview, result_data,
                   error_message, published_at, adapter_name
            FROM {_TABLE_NAME}
            WHERE {where_clause}
            ORDER BY published_at DESC, id DESC
            LIMIT ?
            """  # noqa: S608
        rows = await db.fetchall(
            statement,
            parameters,
        )
        return [_record_from_row(row) for row in rows]


def _record_from_row(row: aiosqlite.Row) -> PublishRecord:
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
    )


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
