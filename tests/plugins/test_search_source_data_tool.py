"""Tests for the SearchSourceDataTool RAG + preference filtering handler."""

from __future__ import annotations

import pytest

from multiscribe_agent.domain.models import UnifiedData
from multiscribe_agent.infra.db import init_db
from multiscribe_agent.memory.memory_service import MemoryService
from multiscribe_agent.memory.preference_store import (
    DEFAULT_PREFERENCES,
    PreferenceStore,
    UserPreferences,
)
from multiscribe_agent.memory.repositories.memory_categories import MemoryCategoryRepository
from multiscribe_agent.plugins.builtin.tools.search_source_data import SearchSourceDataTool
from multiscribe_agent.rag.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    RetrievalScope,
    RetrievedEvidence,
)
from multiscribe_agent.services.candidate_filter import CandidateFilter


def _item(
    item_id: str,
    title: str,
    *,
    source: str = "rss",
    description: str | None = None,
    published_date: str = "2026-07-16",
) -> UnifiedData:
    """Build one normalized source item for a RAG evidence fixture."""
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


def _evidence(item: UnifiedData) -> RetrievedEvidence:
    """Convert one fixture item to a source-data RAG evidence record."""
    document = KnowledgeDocument(
        document_id=f"source_data:{item.id}",
        doc_type="source_data",
        title=item.title,
        url=item.url,
        source=item.source,
        category=item.category,
        published_at=item.published_date,
        user_id="admin",
        content_hash="a" * 64,
    )
    return RetrievedEvidence(
        evidence_id=f"evidence:{item.id}",
        chunk=KnowledgeChunk(
            chunk_id=f"source_data:{item.id}:0",
            document_id=document.document_id,
            content=item.description,
            index=0,
        ),
        document=document,
        score=1.0,
        retrieval_source="hybrid",
        scope=RetrievalScope(user_id="admin", doc_types=["source_data"]),
    )


class _FakeRag:
    """Return deterministic evidence without touching the derived index."""

    def __init__(self, evidence: list[RetrievedEvidence]) -> None:
        self._evidence = evidence

    async def retrieve(
        self, query: str, scope: RetrievalScope, *, top_k: int = 10
    ) -> list[RetrievedEvidence]:
        assert query.strip()
        assert scope.user_id == "admin"
        assert scope.doc_types == ["source_data"]
        return self._evidence[:top_k]


async def _build_tool(evidence: list[RetrievedEvidence]) -> SearchSourceDataTool:
    """Return a tool wired to fake RAG and persisted preferences."""
    memory = await _build_memory_with_preferences(DEFAULT_PREFERENCES)
    return SearchSourceDataTool(_FakeRag(evidence), memory, CandidateFilter(20))


@pytest.mark.asyncio
async def test_search_returns_ranked_results() -> None:
    """RAG evidence is mapped to the stable id/title/summary/url/source shape."""
    items = [
        _item("a", "Artificial intelligence advances"),
        _item("b", "Database systems news"),
    ]
    tool = await _build_tool([_evidence(item) for item in items])
    result = await tool.handler({"query": "intelligence"})

    assert isinstance(result, dict)
    assert result["query"] == "intelligence"
    assert result["returned"] == 2
    assert result["blocked"] == 0
    item = result["results"][0]
    assert item["id"] == "a"
    assert item["title"] == "Artificial intelligence advances"
    assert item["url"] == "https://example.com/a"
    assert item["source"] == "rss"
    assert "intelligence" in item["summary"].lower()


@pytest.mark.asyncio
async def test_search_applies_preference_filtering() -> None:
    """Preferred tags rank higher; blocked sources/topics are counted."""
    items = [
        _item("ai", "Generic content about RAG", source="rss"),
        _item("noise", "Generic content about trending", source="github_trending"),
        _item("boring", "Generic content about funding announcement", source="rss"),
    ]
    memory = await _build_memory_with_preferences(
        UserPreferences(
            preferred_tags=["rag"],
            block_sources=["github_trending"],
            blocked_topics=["funding announcement"],
            push_time="09:00",
            importance_threshold=0,
        )
    )
    tool = SearchSourceDataTool(
        _FakeRag([_evidence(item) for item in items]), memory, CandidateFilter(20)
    )
    result = await tool.handler({"query": "content", "limit": 20})

    assert result["blocked"] == 2
    assert result["returned"] == 1
    assert result["results"][0]["id"] == "ai"


@pytest.mark.asyncio
async def test_search_rejects_empty_query() -> None:
    """An empty query is rejected with a non-fatal error string."""
    tool = await _build_tool([])
    result = await tool.handler({"query": ""})
    assert result == "Error: query must not be empty"


@pytest.mark.asyncio
async def test_search_returns_empty_when_no_match() -> None:
    """A query with no RAG evidence returns an empty stable result."""
    tool = await _build_tool([])
    result = await tool.handler({"query": "nonexistent_xyzzy_phrase"})
    assert result == {
        "query": "nonexistent_xyzzy_phrase",
        "results": [],
        "returned": 0,
        "blocked": 0,
    }


@pytest.mark.asyncio
async def test_search_swallows_rag_exception() -> None:
    """A RAG failure is isolated and returns an empty result."""

    class _Boom:
        async def retrieve(
            self, query: str, scope: RetrievalScope, *, top_k: int = 10
        ) -> list[RetrievedEvidence]:
            del query, scope, top_k
            raise RuntimeError("rag unavailable")

    tool = SearchSourceDataTool(_Boom(), None, CandidateFilter(20))
    result = await tool.handler({"query": "anything"})
    assert result == {"query": "anything", "results": [], "returned": 0, "blocked": 0}
