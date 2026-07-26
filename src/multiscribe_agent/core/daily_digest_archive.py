"""Persistent public archive for completed daily AI digests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import cast

import aiosqlite

from multiscribe_agent.infra.db import Database
from multiscribe_agent.renderers.models import CuratedDigest

_TABLE_NAME = "daily_digest_archives"
_MAX_QUERY_LIMIT = 366


@dataclass(frozen=True, slots=True)
class ArchivedDigestItem:
    """One safe, user-facing item stored in a daily digest archive."""

    title: str
    summary: str
    url: str
    source: str
    score: float | None
    image_url: str | None = None
    video_url: str | None = None
    published_at: str | None = None
    section: str = "产品与功能更新"
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ArchivedDigest:
    """One complete daily digest prepared for the public reading page."""

    date: str
    title: str
    summary: str
    items: list[ArchivedDigestItem]
    total_scanned: int
    updated_at: datetime


class DailyDigestArchive:
    """Upsert and query generated daily digests through the application database."""

    async def upsert(self, db: Database, digest: CuratedDigest) -> None:
        """Persist the generated digest even when downstream publishers later fail."""
        date.fromisoformat(digest.date)
        item_payload = [
            {
                "title": item.title,
                "summary": item.summary,
                "url": item.url,
                "source": item.source,
                "score": item.score,
                "image_url": item.image_url,
                "video_url": item.video_url,
                "published_at": item.published_at,
                "section": item.section,
                "tags": list(item.tags),
            }
            for item in digest.items
        ]
        now = datetime.now(UTC).isoformat()
        await db.execute(
            f"""
            INSERT INTO {_TABLE_NAME} (
                digest_date, title, summary, items, total_scanned, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(digest_date) DO UPDATE SET
                title = excluded.title,
                summary = excluded.summary,
                items = excluded.items,
                total_scanned = excluded.total_scanned,
                updated_at = excluded.updated_at
            """,  # noqa: S608 - table name is a module constant.
            (
                digest.date,
                digest.title,
                digest.summary,
                json.dumps(item_payload, ensure_ascii=False, sort_keys=True),
                digest.total_scanned,
                now,
            ),
        )

    async def get(self, db: Database, digest_date: str) -> ArchivedDigest | None:
        """Return one exact archive date, or ``None`` when no digest was generated."""
        date.fromisoformat(digest_date)
        row = await db.fetchone(
            f"""
            SELECT digest_date, title, summary, items, total_scanned, updated_at
            FROM {_TABLE_NAME}
            WHERE digest_date = ?
            """,  # noqa: S608 - table name is a module constant.
            (digest_date,),
        )
        return _record_from_row(row) if row is not None else None

    async def list(self, db: Database, limit: int = 31) -> list[ArchivedDigest]:
        """Return newest archives first within a bounded public-page history."""
        bounded_limit = max(1, min(limit, _MAX_QUERY_LIMIT))
        rows = await db.fetchall(
            f"""
            SELECT digest_date, title, summary, items, total_scanned, updated_at
            FROM {_TABLE_NAME}
            ORDER BY digest_date DESC
            LIMIT ?
            """,  # noqa: S608 - table name is a module constant.
            (bounded_limit,),
        )
        return [_record_from_row(row) for row in rows]


def _record_from_row(row: aiosqlite.Row) -> ArchivedDigest:
    """Decode one trusted SQLite row into the typed public archive contract."""
    decoded: object = json.loads(str(row["items"]))
    if not isinstance(decoded, list):
        raise ValueError("daily digest archive items must be a JSON array")

    items: list[ArchivedDigestItem] = []
    for raw_item in decoded:
        if not isinstance(raw_item, Mapping):
            raise ValueError("daily digest archive item must be a JSON object")
        item = cast(Mapping[str, object], raw_item)
        raw_score = item.get("score")
        score = float(raw_score) if isinstance(raw_score, int | float) else None
        items.append(
            ArchivedDigestItem(
                title=_required_text(item, "title"),
                summary=_required_text(item, "summary"),
                url=_required_text(item, "url"),
                source=_required_text(item, "source"),
                score=score,
                image_url=_optional_text(item.get("image_url")),
                video_url=_optional_text(item.get("video_url")),
                published_at=_optional_text(item.get("published_at")),
                section=_optional_text(item.get("section")) or "产品与功能更新",
                tags=_text_tuple(item.get("tags")),
            )
        )

    return ArchivedDigest(
        date=str(row["digest_date"]),
        title=str(row["title"]),
        summary=str(row["summary"]),
        items=items,
        total_scanned=int(row["total_scanned"]),
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
    )


def _required_text(item: Mapping[str, object], key: str) -> str:
    """Read a non-empty string from a persisted archive item."""
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"daily digest archive item requires {key}")
    return value


def _optional_text(value: object) -> str | None:
    """Read an optional non-empty text field from an archived JSON item."""
    return value.strip() if isinstance(value, str) and value.strip() else None


def _text_tuple(value: object) -> tuple[str, ...]:
    """Decode optional archived tags while ignoring malformed values."""
    if not isinstance(value, list):
        return ()
    return tuple(
        dict.fromkeys(tag.strip() for tag in value if isinstance(tag, str) and tag.strip())
    )


_archive: DailyDigestArchive | None = None


def get_daily_digest_archive() -> DailyDigestArchive:
    """Return the process-local stateless daily digest archive service."""
    global _archive
    if _archive is None:
        _archive = DailyDigestArchive()
    return _archive
