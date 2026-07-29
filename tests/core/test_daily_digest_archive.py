"""P41 approval-state persistence and migration tests."""

from __future__ import annotations

import pytest

from multiscribe_agent.core.daily_digest_archive import DailyDigestArchive
from multiscribe_agent.infra.db import Database, init_db
from multiscribe_agent.renderers.feishu_card import DigestItem
from multiscribe_agent.renderers.models import CuratedDigest


def _digest(date: str = "2026-07-29") -> CuratedDigest:
    """Build a small immutable digest for archive state tests."""
    return CuratedDigest(
        date=date,
        title="AI Daily",
        summary="A concise overview",
        total_scanned=1,
        items=[
            DigestItem(
                title="Agent update",
                summary="A useful update.",
                url="https://example.test/agent",
                source="RSS",
                score=8.0,
            )
        ],
    )


@pytest.mark.asyncio
async def test_archive_schema_and_approval_state_round_trip() -> None:
    """New archives default to published and support all approval transitions."""
    db = await init_db(":memory:")
    try:
        columns = await db.fetchall("PRAGMA table_info(daily_digest_archives)")
        status_column = next(column for column in columns if column["name"] == "approval_status")
        assert status_column["dflt_value"] == "'published'"

        archive = DailyDigestArchive()
        await archive.upsert(db, _digest(), approval_status="pending")
        assert await archive.get_approval_status(db, "2026-07-29") == "pending"
        record = await archive.get(db, "2026-07-29")
        assert record is not None
        assert record.approval_status == "pending"

        for status in ("approved", "rejected", "published"):
            await archive.set_approval_status(db, "2026-07-29", status)
            assert await archive.get_approval_status(db, "2026-07-29") == status
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_archive_migration_adds_status_to_legacy_table() -> None:
    """A pre-P41 table is upgraded without changing existing archive rows."""
    db = await Database.open(":memory:")
    try:
        await db.execute(
            """
            CREATE TABLE daily_digest_archives (
                digest_date TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                items TEXT NOT NULL DEFAULT '[]',
                total_scanned INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            INSERT INTO daily_digest_archives
                (digest_date, title, summary, items, total_scanned, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("2026-07-28", "Legacy", "summary", "[]", 0, "2026-07-28T00:00:00+00:00"),
        )

        await db.migrate_daily_digest_archives()

        archive = DailyDigestArchive()
        assert await archive.get_approval_status(db, "2026-07-28") == "published"
        columns = await db.fetchall("PRAGMA table_info(daily_digest_archives)")
        assert any(column["name"] == "approval_status" for column in columns)
    finally:
        await db.close()
