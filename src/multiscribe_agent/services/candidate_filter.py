"""Reusable candidate filtering and ranking shared by daily_digest and chat tooling."""

from __future__ import annotations

from multiscribe_agent.domain.models import UnifiedData
from multiscribe_agent.memory.preference_store import UserPreferences


class CandidateFilter:
    """Filter candidates by blocked sources/topics and rank by tag-match then recency."""

    def __init__(self, candidate_limit: int) -> None:
        """Store the bounded candidate count for downstream truncation."""
        self._candidate_limit = candidate_limit

    def filter_and_rank(
        self, candidates: list[UnifiedData], preferences: UserPreferences
    ) -> tuple[list[UnifiedData], int]:
        """Apply block filters, rank by tag-match then date, truncate to limit."""
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

    def fallback_rank(self, items: list[UnifiedData]) -> list[UnifiedData]:
        """Prefer the newest source records when no preferences are available."""
        return sorted(items, key=lambda item: item.published_date, reverse=True)[
            : self._candidate_limit
        ]

    @staticmethod
    def _tag_matches(item: UnifiedData, tags: list[str]) -> int:
        """Count how many preferred tags appear in the candidate's textual fields."""
        haystack = " ".join((item.title, item.description, item.category or "")).casefold()
        return sum(tag in haystack for tag in tags)
