"""Bounded durable-memory retrieval for daily digest curation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import structlog

from multiscribe_agent.domain.models import MemoryEntry, UnifiedData
from multiscribe_agent.knowledge.kb_service import KBService
from multiscribe_agent.knowledge.retriever import RetrievalHit
from multiscribe_agent.memory.preference_store import UserPreferences
from multiscribe_agent.services.candidate_filter import CandidateFilter

log = structlog.get_logger(__name__)

MAX_MEMORY_ENTRIES = 5
MAX_MEMORY_CHARS = 1_600
MAX_KB_SNIPPETS = 3
MAX_KB_CHARS = 600


class DigestMemoryService(Protocol):
    """Memory operations consumed by the daily-digest pipeline."""

    async def get_preferences(self) -> UserPreferences:
        """Return the current durable user preferences."""

    async def search_entries(self, query: str, limit: int = 20) -> list[MemoryEntry]:
        """Return FTS matches for one narrow retrieval query."""


class DigestKnowledgeService(Protocol):
    """Knowledge-base retrieval consumed by the daily-digest pipeline."""

    async def search(self, query: str, *, top_k: int = 3) -> list[RetrievalHit]:
        """Return hybrid retrieval hits for one query."""


KBSnippetProvider = Callable[[list[UnifiedData]], list[str]]
"""Optional override that replaces KB retrieval with a precomputed snippet list."""


@dataclass(frozen=True, slots=True)
class DigestMemoryContext:
    """Filtered candidate items and compact summaries ready for prompt injection."""

    items: list[UnifiedData]
    memory_summaries: list[str]
    blocked_count: int
    kb_snippets: list[str]
    preferred_tags: list[str]
    blocked_topics: list[str]


class DigestMemoryContextBuilder:
    """Apply hard constraints, rank candidates, and retrieve compact relevant memories."""

    def __init__(
        self,
        service: DigestMemoryService,
        candidate_limit: int,
        kb_service: DigestKnowledgeService | KBService | None = None,
        kb_snippet_provider: KBSnippetProvider | None = None,
        candidate_filter: CandidateFilter | None = None,
    ) -> None:
        self._service = service
        self._candidate_limit = candidate_limit
        self._candidate_filter = candidate_filter or CandidateFilter(candidate_limit)
        self._kb_service = kb_service
        self._kb_snippet_provider = kb_snippet_provider

    async def build(self, candidates: list[UnifiedData]) -> DigestMemoryContext:
        """Create a bounded curation context without exposing full memory history."""
        preferences = await self._service.get_preferences()
        items, blocked_count = self._candidate_filter.filter_and_rank(candidates, preferences)
        memories = await self._retrieve_memories(items, preferences)
        kb_snippets = await self._retrieve_kb_snippets(items)
        return DigestMemoryContext(
            items=items,
            memory_summaries=self._summaries(memories),
            blocked_count=blocked_count,
            kb_snippets=kb_snippets,
            preferred_tags=list(preferences.preferred_tags),
            blocked_topics=list(preferences.blocked_topics),
        )

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

    async def _retrieve_kb_snippets(self, items: list[UnifiedData]) -> list[str]:
        """Pull bounded snippets from the knowledge base when available."""
        if self._kb_snippet_provider is not None:
            try:
                snippets = list(self._kb_snippet_provider(items))
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                log.warning(
                    "daily_digest_kb_snippets_failed",
                    error_type=type(exc).__name__,
                )
                return []
            return self._bound_snippets(snippets)
        if self._kb_service is None:
            return []
        queries = self._kb_queries(items)
        kb_snippets: list[str] = []
        seen: set[str] = set()
        for query in queries:
            try:
                hits = await self._kb_service.search(query, top_k=2)
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                log.warning(
                    "daily_digest_kb_search_failed",
                    query=query[:80],
                    error_type=type(exc).__name__,
                )
                return self._bound_snippets(kb_snippets)
            for hit in hits:
                text = " ".join(hit.content.split())
                if not text or text in seen:
                    continue
                seen.add(text)
                kb_snippets.append(text)
                if len(kb_snippets) >= MAX_KB_SNIPPETS * 3:
                    break
            if len(kb_snippets) >= MAX_KB_SNIPPETS * 3:
                break
        return self._bound_snippets(kb_snippets)

    @staticmethod
    def _kb_queries(items: list[UnifiedData]) -> list[str]:
        """Build a bounded set of KB queries from candidate titles and categories."""
        queries: list[str] = []
        seen: set[str] = set()
        for item in items:
            for raw in (item.title, item.category or ""):
                query = raw.strip()
                if not query:
                    continue
                key = query.casefold()
                if key in seen:
                    continue
                seen.add(key)
                queries.append(query)
                if len(queries) >= 4:
                    return queries
        return queries

    @staticmethod
    def _bound_snippets(snippets: list[str]) -> list[str]:
        """Bound the snippet list to the configured limit and total character budget."""
        bounded: list[str] = []
        used = 0
        for raw in snippets:
            text = raw.strip()
            if not text:
                continue
            remaining = MAX_KB_CHARS - used
            if remaining <= 0:
                break
            chunk = text[:remaining]
            bounded.append(chunk)
            used += len(chunk)
            if len(bounded) >= MAX_KB_SNIPPETS:
                break
        return bounded

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
