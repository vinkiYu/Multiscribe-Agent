"""Durable user preference storage backed by a dedicated memory category."""

from __future__ import annotations

from dataclasses import dataclass, field

from multiscribe_agent.memory.repositories.memory_categories import MemoryCategoryRepository

PREFERENCES_CATEGORY_ID = "user-preferences"


@dataclass(frozen=True, slots=True)
class UserPreferences:
    """Preferences that steer recommendation and delivery behavior."""

    preferred_tags: list[str]
    block_sources: list[str]
    push_time: str
    importance_threshold: int
    blocked_topics: list[str] = field(default_factory=list)


DEFAULT_PREFERENCES = UserPreferences([], [], "09:00", 5)


class PreferenceStore:
    """Persist user preferences through the isolated category repository."""

    def __init__(
        self,
        categories: MemoryCategoryRepository,
        defaults: UserPreferences = DEFAULT_PREFERENCES,
    ) -> None:
        """Create a preference store using the memory-category repository."""
        self._categories = categories
        self._defaults = defaults

    async def load(self) -> UserPreferences:
        """Return saved preferences or the documented defaults."""
        data = await self._categories.get(PREFERENCES_CATEGORY_ID)
        if data is None:
            return self._defaults
        return _preferences_from_data(data, self._defaults)

    async def save(self, preferences: UserPreferences) -> None:
        """Validate and persist one full preference value."""
        _validate_preferences(preferences)
        await self._categories.save(
            PREFERENCES_CATEGORY_ID,
            {
                "preferred_tags": preferences.preferred_tags,
                "block_sources": preferences.block_sources,
                "blocked_topics": preferences.blocked_topics,
                "push_time": preferences.push_time,
                "importance_threshold": preferences.importance_threshold,
            },
        )


def _preferences_from_data(data: dict[str, object], defaults: UserPreferences) -> UserPreferences:
    """Convert untrusted persisted JSON into one validated preference value."""
    preferred_tags = _string_list(data.get("preferred_tags"))
    block_sources = _string_list(data.get("block_sources"))
    blocked_topics = _string_list(data.get("blocked_topics"))
    push_time = data.get("push_time", defaults.push_time)
    threshold = data.get("importance_threshold", defaults.importance_threshold)
    if not isinstance(push_time, str) or not isinstance(threshold, int):
        raise ValueError("invalid persisted user preferences")
    preferences = UserPreferences(
        preferred_tags,
        block_sources,
        push_time,
        threshold,
        blocked_topics=blocked_topics,
    )
    _validate_preferences(preferences)
    return preferences


def _string_list(value: object) -> list[str]:
    """Normalize an optional persisted string list."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("preference values must be string lists")
    return list(value)


def _validate_preferences(preferences: UserPreferences) -> None:
    """Reject malformed preference values before they reach storage."""
    if len(preferences.push_time) != 5 or preferences.push_time[2] != ":":
        raise ValueError("push_time must use HH:MM format")
    hours, minutes = preferences.push_time.split(":")
    valid_numbers = hours.isdigit() and minutes.isdigit()
    valid_range = valid_numbers and 0 <= int(hours) <= 23 and 0 <= int(minutes) <= 59
    if not valid_range:
        raise ValueError("push_time must use HH:MM format")
    if not 0 <= preferences.importance_threshold <= 10:
        raise ValueError("importance_threshold must be between 0 and 10")
