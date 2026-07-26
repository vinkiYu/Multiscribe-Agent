"""Mocked HTTP and local-fixture tests for the RSS adapter."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from multiscribe_agent.plugins.builtin.adapters.rss import RSSAdapter
from multiscribe_agent.plugins.discovery import scan_and_register
from multiscribe_agent.plugins.registry import AdapterRegistry

FIXTURES = Path(__file__).parents[1] / "fixtures"
RSS_URL = "https://feeds.example.test/hackernews.xml"


def fixture_text(name: str) -> str:
    """Read one local XML fixture without external network access."""
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_fetch_transform_and_fetch_and_transform() -> None:
    """Mocked HTTP XML maps to a complete normalized RSS item."""
    adapter = RSSAdapter()
    config = {"rss_url": RSS_URL, "source_name": "HN", "category": "technology"}
    with respx.mock:
        respx.get(RSS_URL).mock(
            return_value=httpx.Response(200, text=fixture_text("hackernews.xml"))
        )
        raw = await adapter.fetch(config)
    items = adapter.transform(raw, config)

    assert len(items) == 1
    item = items[0]
    assert item.id == "hn-1001"
    assert item.title == "Example engineering story"
    assert item.url == "https://example.test/story-1001"
    assert item.source == "HN"
    assert item.category == "technology"
    assert item.published_date == "2026-07-16T08:30:00+00:00"
    assert item.metadata["tags"] == ["engineering", "python"]
    assert item.metadata["image_url"] == "https://cdn.example.test/story-1001.jpg"
    assert item.metadata["video_url"] == "https://cdn.example.test/story-1001.mp4"
    assert item.metadata["feed_url"] == RSS_URL

    with respx.mock:
        respx.get(RSS_URL).mock(
            return_value=httpx.Response(200, text=fixture_text("hackernews.xml"))
        )
        end_to_end = await adapter.fetch_and_transform(config)
    assert [entry.id for entry in end_to_end] == ["hn-1001"]


def test_transform_atom_updated_date_is_normalized() -> None:
    """Atom updated_parsed values also become timezone-aware ISO timestamps."""
    items = RSSAdapter().transform(fixture_text("sample_feed.xml"))

    assert len(items) == 1
    assert items[0].id == "atom-2001"
    assert items[0].published_date == "2026-07-16T09:45:00+00:00"
    assert items[0].source == "Sample Atom Feed"
    assert items[0].metadata["tags"] == ["atom"]


@pytest.mark.asyncio
async def test_network_failure_returns_empty_from_template_method() -> None:
    """HTTP errors are contained by BaseAdapter.fetch_and_transform."""
    with respx.mock:
        respx.get(RSS_URL).mock(side_effect=httpx.ConnectError("offline"))
        items = await RSSAdapter().fetch_and_transform({"rss_url": RSS_URL})

    assert items == []


@pytest.mark.asyncio
async def test_fetch_and_transform_flattens_multiple_configured_feeds() -> None:
    """A scheduled RSS source can aggregate feeds while isolating a failed URL."""
    second_url = "https://feeds.example.test/second.xml"
    with respx.mock:
        respx.get(RSS_URL).mock(
            return_value=httpx.Response(200, text=fixture_text("hackernews.xml"))
        )
        respx.get(second_url).mock(side_effect=httpx.ConnectError("offline"))

        items = await RSSAdapter().fetch_and_transform({"rss_urls": [RSS_URL, second_url]})

    assert [item.id for item in items] == ["hn-1001"]


def test_rss_adapter_is_discovered() -> None:
    """Discovery registers RSSAdapter metadata without constructing a runtime instance."""
    result = scan_and_register()

    assert "multiscribe_agent.plugins.builtin.adapters.rss.RSSAdapter" in result.registered
    assert any(metadata.id == "rss" for metadata in AdapterRegistry.get_instance().list_metadata())


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_real_rss_fetch_is_manual_only() -> None:
    """Reserve a separately marked slot for manual network verification."""
    pytest.skip("manual e2e requires an explicitly selected live RSS URL")
