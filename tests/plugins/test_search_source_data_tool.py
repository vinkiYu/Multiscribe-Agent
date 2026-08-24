"""Tests for the SearchSourceDataTool FTS + preference filtering handler."""

from __future__ import annotations

import pytest

from multiscribe_agent.domain.models import UnifiedData
from multiscribe_agent.infra.db import init_db
from multiscribe_agent.infra.repositories.source_data import SourceDataRepository
from multiscribe_agent.memory.memory_service import MemoryService
from multiscribe_agent.memory.preference_store import (
    DEFAULT_PREFERENCES,
    PreferenceStore,
    UserPreferences,
)
from multiscribe_agent.memory.repositories.memory_categories import MemoryCategoryRepository
from multiscribe_agent.plugins.builtin.tools.search_source_data import SearchSourceDataTool
from multiscribe_agent.services.candidate_filter import CandidateFilter


def _item(
    item_id: str,
    title: str,
    *,
    source: str = "rss",
    description: str | None = None,
    published_date: str = "2026-07-16",
) -> UnifiedData:
    """Build a minimal UnifiedData shaped for the FTS seed."""
    return UnifiedData(
        id=item_id,
        title=title,
        url=f"https://example.com/{item_id}",
        description=description or f"{title} searchable description",
        published_date=published_date,
        ingestion_date=published_date,
        source=source,
        category="news",
        metadata={"ai_summary": f"{title} summary"},
    )


async def _build_memory_with_preferences(preferences: UserPreferences) -> MemoryService:
    """Return a MemoryService backed by an in-memory preference store."""
    db = await init_db(":memory:")
    category_repo = MemoryCategoryRepository(db)
    store = PreferenceStore(category_repo)
    await store.save(preferences)
    from multiscribe_agent.memory.repositories.memory_entries import MemoryEntryRepository

    return MemoryService(
        MemoryEntryRepository(db),
        store,
        extractor=None,  # type: ignore[arg-type]
        kb_service=None,
    )


async def _build_tool_with_repo(repository: SourceDataRepository) -> SearchSourceDataTool:
    """Return a tool wired to a real repo and the default memory service (None fallback)."""
    memory = await _build_memory_with_preferences(DEFAULT_PREFERENCES)
    return SearchSourceDataTool(repository, memory, CandidateFilter(20))


@pytest.mark.asyncio
async def test_search_returns_ranked_results() -> None:
    """A normal FTS query returns ranked candidates with id/title/summary/url/source."""
    db = await init_db(":memory:")
    repository = SourceDataRepository(db)
    await repository.save_batch(
        [
            _item("a", "Artificial intelligence advances"),
            _item("b", "Database systems news"),
        ],
        "rss-adapter",
    )

    tool = await _build_tool_with_repo(repository)
    try:
        result = await tool.handler({"query": "intelligence"})
    finally:
        await db.close()

    assert isinstance(result, dict)
    assert result["query"] == "intelligence"
    assert result["returned"] == 1
    assert result["blocked"] == 0
    assert len(result["results"]) == 1
    item = result["results"][0]
    assert item["id"] == "a"
    assert item["title"] == "Artificial intelligence advances"
    assert item["url"] == "https://example.com/a"
    assert item["source"] == "rss"
    assert "<mark>intelligence</mark>" in item["summary"].lower()  # FTS highlight preserved


@pytest.mark.asyncio
async def test_search_applies_preference_filtering() -> None:
    """Preferred tags rank higher; block_sources drops items and counts in `blocked`."""
    db = await init_db(":memory:")
    repository = SourceDataRepository(db)
    # Three items all under a shared keyword cohort so the single FTS query hits all of them.
    await repository.save_batch(
        [
            _item("ai", "Generic content about RAG", source="rss", published_date="2026-07-16"),
            _item(
                "noise",
                "Generic content about trending",
                source="github_trending",
                published_date="2026-07-16",
            ),
            _item(
                "boring",
                "Generic content about funding announcement",
                source="rss",
                published_date="2026-07-16",
            ),
        ],
        "rss-adapter",
    )

    memory = await _build_memory_with_preferences(
        UserPreferences(
            preferred_tags=["rag"],
            block_sources=["github_trending"],
            blocked_topics=["funding announcement"],
            push_time="09:00",
            importance_threshold=0,
        )
    )
    tool = SearchSourceDataTool(repository, memory, CandidateFilter(20))
    try:
        result = await tool.handler({"query": "content", "limit": 20})
    finally:
        await db.close()

    # The github_trending noise and the funding announcement are both dropped.
    assert result["blocked"] == 2
    # The RAG item survives and is the only result.
    assert result["returned"] == 1
    assert result["results"][0]["id"] == "ai"


@pytest.mark.asyncio
async def test_search_rejects_empty_query() -> None:
    """An empty query is rejected with a non-fatal error string."""
    db = await init_db(":memory:")
    repository = SourceDataRepository(db)
    tool = await _build_tool_with_repo(repository)
    try:
        result = await tool.handler({"query": ""})
    finally:
        await db.close()
    assert result == "Error: query must not be empty"


@pytest.mark.asyncio
async def test_search_returns_empty_when_no_match() -> None:
    """A query that hits nothing returns results: [] without crashing."""
    db = await init_db(":memory:")
    repository = SourceDataRepository(db)
    await repository.save_batch([_item("a", "Anything")], "rss-adapter")

    tool = await _build_tool_with_repo(repository)
    try:
        result = await tool.handler({"query": "nonexistent_xyzzy_phrase"})
    finally:
        await db.close()

    assert result == {
        "query": "nonexistent_xyzzy_phrase",
        "results": [],
        "returned": 0,
        "blocked": 0,
    }


@pytest.mark.asyncio
async def test_search_swallows_fts_exception() -> None:
    """A malformed FTS query is caught and returns an empty result rather than propagating."""
    db = await init_db(":memory:")
    repository = SourceDataRepository(db)
    await repository.save_batch([_item("a", "Anything")], "rss-adapter")

    class _Boom:
        async def search_fts(self, query: str, limit: int) -> list[object]:
            raise RuntimeError("malformed FTS MATCH expression")

    tool = SearchSourceDataTool(_Boom(), None, CandidateFilter(20))
    try:
        result = await tool.handler({"query": "anything"})
    finally:
        await db.close()

    assert result == {"query": "anything", "results": [], "returned": 0, "blocked": 0}
