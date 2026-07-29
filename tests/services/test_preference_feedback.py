"""Tests for click-driven preferred-tag feedback."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from multiscribe_agent.core.click_events import ClickEventRepository
from multiscribe_agent.infra.db import Database, init_db
from multiscribe_agent.memory.preference_store import UserPreferences
from multiscribe_agent.services.preference_feedback import PreferenceFeedbackService


@dataclass
class FakePreferenceStore:
    """In-memory preference store that records full saves."""

    preferences: UserPreferences
    saves: int = 0

    async def load(self) -> UserPreferences:
        return self.preferences

    async def save(self, preferences: UserPreferences) -> None:
        self.preferences = preferences
        self.saves += 1


async def _add_clicks(db: Database, repo: ClickEventRepository) -> None:
    for tag in ("python", "python", "agent", "rag"):
        await repo.record(
            db,
            digest_date="2026-07-29",
            item_url=f"https://example.test/{tag}",
            item_source="RSS",
            item_tags=[tag],
        )


@pytest.mark.asyncio
async def test_click_feedback_preserves_manual_fields_and_orders_tags() -> None:
    """Manual tags stay first while click tags append by descending frequency."""
    db = await init_db(":memory:")
    try:
        repo = ClickEventRepository()
        store = FakePreferenceStore(UserPreferences(["manual"], ["blocked"], "08:30", 7, ["topic"]))
        await _add_clicks(db, repo)
        added = await PreferenceFeedbackService(repo, store).apply_click_feedback(db)
        assert store.preferences.preferred_tags == ["manual", "python", "agent", "rag"]
        assert store.preferences.block_sources == ["blocked"]
        assert store.preferences.push_time == "08:30"
        assert store.preferences.importance_threshold == 7
        assert store.preferences.blocked_topics == ["topic"]
        assert added == {"python", "agent", "rag"}
        assert store.saves == 1
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_click_feedback_is_bounded_and_skips_unchanged_save() -> None:
    """The max-tag cap applies and a second identical fold is a no-op."""
    db = await init_db(":memory:")
    try:
        repo = ClickEventRepository()
        store = FakePreferenceStore(UserPreferences(["manual", "python"], [], "09:00", 5))
        for tag in ("python", "agent", "rag", "workflow"):
            await repo.record(
                db,
                digest_date="2026-07-29",
                item_url=f"https://example.test/{tag}",
                item_source=None,
                item_tags=[tag],
            )
        service = PreferenceFeedbackService(repo, store, max_tags=3)
        assert await service.apply_click_feedback(db) == {"agent"}
        assert store.preferences.preferred_tags == ["manual", "python", "agent"]
        assert await service.apply_click_feedback(db) == set()
        assert store.saves == 1
    finally:
        await db.close()
