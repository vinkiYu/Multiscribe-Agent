"""Unit tests for the shared CandidateFilter service extracted from daily_digest."""

from __future__ import annotations

from multiscribe_agent.domain.models import UnifiedData
from multiscribe_agent.memory.preference_store import UserPreferences
from multiscribe_agent.services.candidate_filter import CandidateFilter


def _candidate(
    *,
    source: str,
    title: str,
    description: str = "",
    category: str = "ai",
    published_date: str = "2026-08-01T00:00:00+00:00",
) -> UnifiedData:
    """Build a minimal UnifiedData with sensible defaults for ranking tests."""
    return UnifiedData(
        id=f"id-{title}",
        title=title,
        url=f"https://example.test/{title}",
        description=description,
        published_date=published_date,
        source=source,
        category=category,
    )


def _preferences(
    *,
    preferred_tags: list[str] | None = None,
    block_sources: list[str] | None = None,
    blocked_topics: list[str] | None = None,
) -> UserPreferences:
    """Return a UserPreferences carrying only the fields the filter inspects."""
    return UserPreferences(
        preferred_tags=preferred_tags or [],
        block_sources=block_sources or [],
        blocked_topics=blocked_topics or [],
        push_time="09:00",
        importance_threshold=0,
    )


def test_block_sources_filters_and_counts() -> None:
    """Items from blocked sources are dropped; other items survive; blocked_count reflects drops."""
    filter_ = CandidateFilter(candidate_limit=10)
    candidates = [
        _candidate(source="github_trending", title="a"),
        _candidate(source="rss_feed", title="b"),
        _candidate(source="github_trending", title="c"),
    ]

    items, blocked = filter_.filter_and_rank(
        candidates, _preferences(block_sources=["github_trending"])
    )

    assert [item.title for item in items] == ["b"]
    assert blocked == 2


def test_blocked_topics_substring_casefold() -> None:
    """blocked_topics match a case-insensitive substring of title+description+source+category."""
    filter_ = CandidateFilter(candidate_limit=10)
    candidates = [
        _candidate(
            source="rss",
            title="LLM release",
            description="model roundup",
            category="news",
            published_date="2026-08-01",
        ),
        _candidate(
            source="rss",
            title="Funding announcement",
            description="big round",
            category="news",
            published_date="2026-08-05",
        ),
        _candidate(
            source="rss",
            title="RAG deep dive",
            description="how to build",
            category="news",
            published_date="2026-08-03",
        ),
    ]

    items, blocked = filter_.filter_and_rank(
        candidates,
        _preferences(blocked_topics=["FUNDING ANNOUNCEMENT"]),  # case-insensitive
    )

    # Only the "Funding announcement" item is dropped on the casefold substring match.
    titles = [item.title for item in items]
    assert "Funding announcement" not in titles
    assert blocked == 1
    # Survivors sorted newest first by published_date.
    assert titles == ["RAG deep dive", "LLM release"]


def test_preferred_tags_weight_ranking() -> None:
    """Items with more preferred-tag matches rank first; equal matches use published_date."""
    filter_ = CandidateFilter(candidate_limit=10)
    candidates = [
        _candidate(
            source="rss",
            title="RAG only",
            description="RAG best practices",
            published_date="2026-08-01",
        ),
        _candidate(
            source="rss",
            title="RAG and Agent",
            description="RAG + Agent overview",
            published_date="2026-08-03",
        ),
    ]

    items, _ = filter_.filter_and_rank(candidates, _preferences(preferred_tags=["rag", "agent"]))

    # Both candidates match both tags (match=2), so secondary key is published_date desc.
    assert [item.title for item in items] == ["RAG and Agent", "RAG only"]


def test_candidate_limit_truncation() -> None:
    """Permitted items are truncated to candidate_limit; blocked_count stays unchanged."""
    filter_ = CandidateFilter(candidate_limit=2)
    candidates = [
        _candidate(source="rss", title="one", published_date="2026-08-01"),
        _candidate(source="rss", title="two", published_date="2026-08-02"),
        _candidate(source="rss", title="three", published_date="2026-08-03"),
        _candidate(source="github_trending", title="blocked"),
    ]

    items, blocked = filter_.filter_and_rank(
        candidates, _preferences(block_sources=["github_trending"])
    )

    # 3 permitted, kept top 2; 1 blocked from github_trending.
    assert [item.title for item in items] == ["three", "two"]
    assert blocked == 1


def test_fallback_rank_newest_first() -> None:
    """fallback_rank returns newest items by published_date, truncated to candidate_limit."""
    filter_ = CandidateFilter(candidate_limit=2)
    candidates = [
        _candidate(source="rss", title="older", published_date="2026-07-01"),
        _candidate(source="rss", title="newest", published_date="2026-08-15"),
        _candidate(source="rss", title="middle", published_date="2026-08-05"),
    ]

    items = filter_.fallback_rank(candidates)

    assert [item.title for item in items] == ["newest", "middle"]


def test_empty_preferences_no_filter() -> None:
    """Empty preferences produce no blocking; items are sorted by date only (newest first)."""
    filter_ = CandidateFilter(candidate_limit=10)
    candidates = [
        _candidate(source="rss", title="older", published_date="2026-07-01"),
        _candidate(source="rss", title="newer", published_date="2026-08-01"),
    ]

    items, blocked = filter_.filter_and_rank(candidates, _preferences())

    assert [item.title for item in items] == ["newer", "older"]
    assert blocked == 0
