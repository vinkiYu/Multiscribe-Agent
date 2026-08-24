"""Collect configured blocked sources and filter candidates before curation."""

from __future__ import annotations

from collections.abc import Iterable

from multiscribe_agent.domain.models import UnifiedData


class BlockedSourceFilter:
    """Casefold-aware source blacklist applied during daily-digest ingest."""

    def __init__(self, sources: Iterable[str]) -> None:
        """Capture a snapshot of blocked sources in casefold form."""
        self._blocked: frozenset[str] = frozenset(
            source.casefold() for source in sources if source and source.strip()
        )

    @property
    def blocked(self) -> frozenset[str]:
        """Return the active blocked source set for diagnostics."""
        return self._blocked

    def is_blocked(self, source: str) -> bool:
        """Return whether one source string should be excluded by the filter."""
        return source.casefold() in self._blocked

    def filter_items(self, items: list[UnifiedData]) -> tuple[list[UnifiedData], int]:
        """Drop blocked-source items and report how many were removed."""
        if not self._blocked:
            return list(items), 0
        kept: list[UnifiedData] = []
        blocked = 0
        for item in items:
            if self.is_blocked(item.source):
                blocked += 1
                continue
            kept.append(item)
        return kept, blocked
