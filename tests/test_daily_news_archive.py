"""Persistence and public API coverage for daily AI news archives."""

from __future__ import annotations

import httpx
import pytest

from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings
from multiscribe_agent.core.daily_digest_archive import DailyDigestArchive
from multiscribe_agent.infra.db import init_db
from multiscribe_agent.renderers.feishu_card import DigestItem
from multiscribe_agent.renderers.models import CuratedDigest


def _digest(digest_date: str, title: str = "AI News") -> CuratedDigest:
    """Build one representative generated digest without external services."""
    return CuratedDigest(
        date=digest_date,
        title=title,
        summary=f"{digest_date} overview",
        total_scanned=12,
        items=[
            DigestItem(
                title=f"{title} item",
                summary="A concise generated summary.",
                url="https://example.test/news",
                source="RSS",
                score=8.5,
                image_url="https://example.test/news.jpg",
                video_url="https://example.test/news.mp4",
                published_at="2026-07-24T08:30:00+00:00",
                tags=("AI", "Agent"),
            )
        ],
    )


@pytest.mark.asyncio
async def test_archive_upsert_replaces_same_date_and_lists_newest_first() -> None:
    """A rerun updates one date atomically without creating duplicate navigation rows."""
    db = await init_db(":memory:")
    try:
        archive = DailyDigestArchive()
        await archive.upsert(db, _digest("2026-07-23", "Older"))
        await archive.upsert(db, _digest("2026-07-24", "Initial"))
        await archive.upsert(db, _digest("2026-07-24", "Refined"))

        records = await archive.list(db)
        selected = await archive.get(db, "2026-07-24")

        assert [record.date for record in records] == ["2026-07-24", "2026-07-23"]
        assert selected is not None
        assert selected.title == "Refined"
        assert selected.items[0].score == 8.5
        assert selected.items[0].image_url == "https://example.test/news.jpg"
        assert selected.items[0].video_url == "https://example.test/news.mp4"
        assert selected.items[0].tags == ("AI", "Agent")
        assert selected.total_scanned == 12
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_database_initialization_creates_daily_digest_archive_table() -> None:
    """Normal database startup idempotently provisions the archive table."""
    db = await init_db(":memory:")
    try:
        row = await db.fetchone(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'daily_digest_archives'"
        )

        assert row is not None
        await db.migrate_daily_digest_archives()
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_public_api_returns_latest_and_requested_daily_news(tmp_path) -> None:
    """The website can read safe archive data without a workbench JWT."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "daily-news.sqlite"))
    context = ServiceContext(settings)
    await context.init()
    try:
        assert context.db is not None
        archive = DailyDigestArchive()
        await archive.upsert(context.db, _digest("2026-07-23", "Older"))
        await archive.upsert(context.db, _digest("2026-07-24", "Latest"))
        app = create_app(settings, context)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            latest = await client.get("/api/daily-news")
            requested = await client.get("/api/daily-news", params={"date": "2026-07-23"})
            missing = await client.get("/api/daily-news", params={"date": "2026-07-22"})

        assert latest.status_code == 200
        assert latest.json()["digest"]["title"] == "Latest"
        assert latest.json()["digest"]["items"][0]["image_url"] == "https://example.test/news.jpg"
        assert latest.json()["digest"]["items"][0]["video_url"] == "https://example.test/news.mp4"
        assert [entry["date"] for entry in latest.json()["archives"]] == [
            "2026-07-24",
            "2026-07-23",
        ]
        assert requested.status_code == 200
        assert requested.json()["digest"]["title"] == "Older"
        assert missing.status_code == 404
    finally:
        await context.close()
