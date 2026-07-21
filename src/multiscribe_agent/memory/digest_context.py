"""Bounded durable-memory retrieval for daily digest curation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from multiscribe_agent.domain.models import MemoryEntry, UnifiedData
from multiscribe_agent.memory.preference_store import UserPreferences

MAX_MEMORY_ENTRIES = 5
MAX_MEMORY_CHARS = 1_600


class DigestMemoryService(Protocol):
    """Memory operations consumed by the daily-digest pipeline."""

    async def get_preferences(self) -> UserPreferences:
        """Return the current durable user preferences."""

    async def search_entries(self, query: str, limit: int = 20) -> list[MemoryEntry]:
        """Return FTS matches for one narrow retrieval query."""


@dataclass(frozen=True, slots=True)
class DigestMemoryContext:
    """Filtered candidate items and compact summaries ready for prompt injection."""

    items: list[UnifiedData]
    memory_summaries: list[str]
    blocked_count: int


class DigestMemoryContextBuilder:
    """Apply hard constraints, rank candidates, and retrieve compact relevant memories."""

    def __init__(self, service: DigestMemoryService, candidate_limit: int) -> None:
        self._service = service
        self._candidate_limit = candidate_limit

    async def build(self, candidates: list[UnifiedData]) -> DigestMemoryContext:
        """Create a bounded curation context without exposing full memory history."""
        preferences = await self._service.get_preferences()
        items, blocked_count = self._filter_and_rank(candidates, preferences)
        memories = await self._retrieve_memories(items, preferences)
        return DigestMemoryContext(items, self._summaries(memories), blocked_count)

    def _filter_and_rank(
        self, candidates: list[UnifiedData], preferences: UserPreferences
    ) -> tuple[list[UnifiedData], int]:
        blocked_sources = {value.casefold() for value in preferences.block_sources if value.strip()}
        blocked_topics = [value.casefold() for value in preferences.blocked_topics if value.strip()]
        permitted: list[UnifiedData] = []
        blocked_count = 0
        for item in candidates:
            haystack = " ".join(
                (item.title, item.description, item.source, item.category or "")
            ).casefold()
            if item.source.casefold() in blocked_sources or any(
                topic in haystack for topic in blocked_topics
            ):
                blocked_count += 1
                continue
            permitted.append(item)
        tags = [tag.casefold() for tag in preferences.preferred_tags if tag.strip()]
        permitted.sort(
            key=lambda item: (self._tag_matches(item, tags), item.published_date), reverse=True
        )
        return permitted[: self._candidate_limit], blocked_count

    async def _retrieve_memories(
        self, items: list[UnifiedData], preferences: UserPreferences
    ) -> list[MemoryEntry]:
        queries = list(
            dict.fromkeys(tag.strip() for tag in preferences.preferred_tags if tag.strip())
        )
        queries.extend(
            item.category.strip() for item in items if item.category and item.category.strip()
        )
        queries = list(dict.fromkeys(queries))[:5]
        matched: dict[str, MemoryEntry] = {}
        for query in queries:
            for entry in await self._service.search_entries(query, limit=10):
                if entry.importance >= preferences.importance_threshold:
                    matched[entry.id] = entry
        now = datetime.now(UTC).timestamp()
        tags = [tag.casefold() for tag in preferences.preferred_tags if tag.strip()]
        return sorted(
            matched.values(),
            key=lambda entry: self._memory_score(entry, tags, now),
            reverse=True,
        )[:MAX_MEMORY_ENTRIES]

    @staticmethod
    def _tag_matches(item: UnifiedData, tags: list[str]) -> int:
        haystack = " ".join((item.title, item.description, item.category or "")).casefold()
        return sum(tag in haystack for tag in tags)

    @staticmethod
    def _memory_score(entry: MemoryEntry, tags: list[str], now: float) -> float:
        tag_matches = sum(tag in {value.casefold() for value in entry.tags} for tag in tags)
        age_days = max(0.0, (now - entry.created_at) / 86_400)
        trusted = entry.metadata.get("trusted") is True
        return (
            entry.importance * 10
            + tag_matches * 50
            + max(0.0, 20 - age_days)
            + (30 if trusted else 0)
        )

    @staticmethod
    def _summaries(entries: list[MemoryEntry]) -> list[str]:
        summaries: list[str] = []
        used = 0
        for entry in entries:
            tags = ", ".join(entry.tags[:5])
            text = " ".join(entry.content.split())
            prefix = f"Preference memory (importance={entry.importance}; tags={tags}): "
            remaining = MAX_MEMORY_CHARS - used - len(prefix)
            if remaining <= 0:
                break
            summary = prefix + text[:remaining]
            summaries.append(summary)
            used += len(summary)
        return summaries
