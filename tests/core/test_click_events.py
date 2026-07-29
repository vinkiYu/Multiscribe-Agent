"""Tests for public digest click persistence and aggregation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from multiscribe_agent.core.click_events import ClickEventRepository
from multiscribe_agent.infra.db import init_db


@pytest.mark.asyncio
async def test_record_persists_json_tags_and_metadata() -> None:
    """A click stores normalized tags and request metadata."""
    db = await init_db(":memory:")
    try:
        columns = await db.fetchall("PRAGMA table_info(click_events)")
        assert {str(column["name"]) for column in columns} >= {
            "digest_date",
            "item_url",
            "item_tags",
            "clicked_at",
        }
        indexes = await db.fetchall("PRAGMA index_list(click_events)")
        assert {str(index["name"]) for index in indexes} >= {
            "idx_click_events_clicked_at",
            "idx_click_events_item_url",
        }
        await ClickEventRepository().record(
            db,
            digest_date="2026-07-29",
            item_url="https://example.test/item",
            item_source="RSS",
            item_tags=["agent", " agent ", "rag"],
            user_agent="test-agent",
            referer="https://example.test/digest",
        )
        row = await db.fetchone("SELECT * FROM click_events")
        assert row is not None
        assert row["item_tags"] == '["agent", "rag"]'
        assert row["user_agent"] == "test-agent"
        assert row["referer"] == "https://example.test/digest"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_tag_click_counts_filters_window_and_minimum() -> None:
    """Only clicks in the inclusive date window contribute to filtered counts."""
    db = await init_db(":memory:")
    try:
        repo = ClickEventRepository()
        await repo.record(
            db,
            digest_date="2026-07-29",
            item_url="https://example.test/one",
            item_source=None,
            item_tags=["agent", "rag"],
        )
        await repo.record(
            db,
            digest_date="2026-07-28",
            item_url="https://example.test/two",
            item_source=None,
            item_tags=["agent", "python"],
        )
        await repo.record(
            db,
            digest_date="2026-07-20",
            item_url="https://example.test/old",
            item_source=None,
            item_tags=["agent"],
        )
        await db.execute(
            "UPDATE click_events SET clicked_at = ? WHERE item_url = ?",
            ((datetime.now(UTC) - timedelta(days=10)).isoformat(), "https://example.test/old"),
        )
        since_date = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
        assert await repo.tag_click_counts(db, since_date=since_date) == {
            "agent": 2,
            "rag": 1,
            "python": 1,
        }
        assert await repo.tag_click_counts(db, since_date=since_date, min_clicks=2) == {"agent": 2}
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_tag_click_counts_ignores_invalid_json_and_empty_tags() -> None:
    """Malformed legacy rows cannot break feedback aggregation."""
    db = await init_db(":memory:")
    try:
        await db.execute(
            """
            INSERT INTO click_events(digest_date, item_url, item_tags, clicked_at)
            VALUES (?, ?, ?, ?)
            """,
            ("2026-07-29", "https://example.test/item", "not-json", "2026-07-29T00:00:00Z"),
        )
        await db.execute(
            """
            INSERT INTO click_events(digest_date, item_url, item_tags, clicked_at)
            VALUES (?, ?, ?, ?)
            """,
            ("2026-07-29", "https://example.test/item", '["", "  "]', "2026-07-29T00:00:00Z"),
        )
        today = datetime.now(UTC).date().isoformat()
        assert await ClickEventRepository().tag_click_counts(db, since_date=today) == {}
    finally:
        await db.close()
