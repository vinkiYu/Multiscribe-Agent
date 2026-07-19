"""Preference persistence tests."""

from __future__ import annotations

import pytest

from multiscribe_agent.memory.preference_store import (
    DEFAULT_PREFERENCES,
    PreferenceStore,
    UserPreferences,
)
from multiscribe_agent.memory.repositories.memory_categories import MemoryCategoryRepository


@pytest.mark.asyncio
async def test_preferences_default_then_round_trip(category_repo: MemoryCategoryRepository) -> None:
    """Absent preferences use defaults and persisted values round-trip."""
    store = PreferenceStore(category_repo)
    assert await store.load() == DEFAULT_PREFERENCES
    expected = UserPreferences(["ai"], ["blocked"], "18:30", 8)
    await store.save(expected)
    assert await store.load() == expected


@pytest.mark.asyncio
async def test_preferences_reject_invalid_push_time(
    category_repo: MemoryCategoryRepository,
) -> None:
    """Malformed delivery times are rejected before persistence."""
    with pytest.raises(ValueError, match="HH:MM"):
        await PreferenceStore(category_repo).save(UserPreferences([], [], "25:00", 5))
