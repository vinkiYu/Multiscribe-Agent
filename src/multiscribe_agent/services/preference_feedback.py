"""Fold click signals and recent publish-history outcomes into durable user preferences."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from multiscribe_agent.core.click_events import ClickEventRepository
from multiscribe_agent.infra.db import Database
from multiscribe_agent.memory.extractor import PreferenceExtractor
from multiscribe_agent.memory.preference_store import PreferenceStore, UserPreferences


class PreferenceFeedbackService:
    """Merge recent click tags and publish-history extractions without overwriting manual fields."""

    def __init__(
        self,
        click_repo: ClickEventRepository,
        preference_store: PreferenceStore,
        extractor: PreferenceExtractor | None = None,
        *,
        window_days: int = 7,
        max_tags: int = 20,
    ) -> None:
        """Configure the feedback window, history extractor, and bounded preference list."""
        if window_days < 1:
            raise ValueError("window_days must be at least 1")
        if max_tags < 1:
            raise ValueError("max_tags must be at least 1")
        self._click_repo = click_repo
        self._preference_store = preference_store
        self._extractor = extractor
        self._window_days = window_days
        self._max_tags = max_tags

    async def apply_click_feedback(self, db: Database) -> set[str]:
        """Apply only click-tag feedback; kept for backward-compatible test doubles."""
        return await self._apply_click_feedback(db)

    async def apply_signals_and_history(self, db: Database) -> set[str]:
        """Extract history into memory and merge recent clicks into the durable preference store."""
        added_tags = await self._apply_click_feedback(db)
        if self._extractor is None:
            return added_tags
        try:
            entries = await self._extractor.extract_from_history(days=self._window_days)
        except (
            OSError,
            RuntimeError,
            ValueError,
        ) as exc:  # pragma: no cover - exercised via integration.
            from structlog import get_logger

            get_logger(__name__).warning(
                "preference_history_extraction_failed",
                error_type=type(exc).__name__,
            )
            return added_tags
        # Persist any newly observed history records into the durable memory store. The
        # extractor itself only builds MemoryEntry instances, so this service is the
        # place that turns them into long-lived state.
        from multiscribe_agent.memory.repositories.memory_entries import MemoryEntryRepository

        await MemoryEntryRepository(db).save_batch(entries)
        return added_tags

    async def _apply_click_feedback(self, db: Database) -> set[str]:
        """Load recent clicks, append ranked tags, and return newly added tags."""
        since_date = (datetime.now(UTC).date() - timedelta(days=self._window_days - 1)).isoformat()
        counts = await self._click_repo.tag_click_counts(db, since_date=since_date)
        preferences = await self._preference_store.load()
        manual_tags = set(preferences.preferred_tags)
        ranked = sorted(counts, key=lambda tag: (-counts[tag], tag.casefold()))
        merged = list(dict.fromkeys([*preferences.preferred_tags, *ranked]))[: self._max_tags]
        if merged == preferences.preferred_tags:
            return set()
        await self._preference_store.save(
            UserPreferences(
                preferred_tags=merged,
                block_sources=list(preferences.block_sources),
                push_time=preferences.push_time,
                importance_threshold=preferences.importance_threshold,
                blocked_topics=list(preferences.blocked_topics),
            )
        )
        return set(merged) - manual_tags
