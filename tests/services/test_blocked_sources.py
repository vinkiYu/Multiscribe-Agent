"""Unit tests for the BlockedSourceFilter service."""

from __future__ import annotations

from multiscribe_agent.domain.models import UnifiedData
from multiscribe_agent.services.blocked_sources import BlockedSourceFilter


def _item(item_id: str, source: str) -> UnifiedData:
    """Build a minimal UnifiedData for source filtering tests."""
    return UnifiedData(
        id=item_id,
        title=f"Title {item_id}",
        url=f"https://example.test/{item_id}",
        description="x",
        published_date="2026-07-17T08:00:00+00:00",
        source=source,
        category="technology",
    )


def test_empty_blocklist_keeps_everything() -> None:
    """No blocked sources means no candidates are dropped."""
    items = [_item("a", "RSS"), _item("b", "github_trending")]
    kept, count = BlockedSourceFilter([]).filter_items(items)
    assert kept == items
    assert count == 0


def test_blocklist_drops_matching_sources_case_insensitively() -> None:
    """Source comparison ignores case so user-entered 'RSS' blocks 'rss' rows."""
    items = [_item("a", "RSS"), _item("b", "github_trending"), _item("c", "rss")]
    kept, count = BlockedSourceFilter(["RSS"]).filter_items(items)
    assert [item.id for item in kept] == ["b"]
    assert count == 2


def test_is_blocked_shortcut_matches_casefold() -> None:
    """is_blocked mirrors the same casefold semantics used by filter_items."""
    blocked = BlockedSourceFilter(["github_trending"])
    assert blocked.is_blocked("GITHUB_TRENDING")
    assert not blocked.is_blocked("huggingface")
    assert blocked.blocked == frozenset({"github_trending"})
