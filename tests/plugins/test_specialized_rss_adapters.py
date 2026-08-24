"""Mocked HTTP tests for the four dedicated RSS adapter subclasses."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from multiscribe_agent.plugins.builtin.adapters.hacker_news import HackerNewsAdapter
from multiscribe_agent.plugins.builtin.adapters.hf_daily_papers import (
    DEFAULT_FEED_URL as HF_DEFAULT_URL,
)
from multiscribe_agent.plugins.builtin.adapters.hf_daily_papers import (
    HFDailyPapersAdapter,
)
from multiscribe_agent.plugins.builtin.adapters.last_week_in_ai import (
    LastWeekInAIAdapter,
)
from multiscribe_agent.plugins.builtin.adapters.tldr_ai import (
    DEFAULT_FEED_URL as TLDR_DEFAULT_URL,
)
from multiscribe_agent.plugins.builtin.adapters.tldr_ai import (
    TLDRAIAdapter,
)
from multiscribe_agent.plugins.discovery import scan_and_register
from multiscribe_agent.plugins.registry import AdapterRegistry

FIXTURES = Path(__file__).parents[1] / "fixtures"


def fixture_text(name: str) -> str:
    """Read one local XML fixture without external network access."""
    return (FIXTURES / name).read_text(encoding="utf-8")


HF_FEED_URL = HF_DEFAULT_URL
TLDR_FEED_URL = TLDR_DEFAULT_URL
HN_FEED_URL = "https://news.ycombinator.com/rss"
LWIA_FEED_URL = "https://www.lastweekin.ai/feed"


@pytest.mark.asyncio
async def test_hf_daily_papers_defaults_apply() -> None:
    """HF adapter emits the documented source name and category without config."""
    adapter = HFDailyPapersAdapter()
    config: dict[str, object] = {}
    with respx.mock:
        respx.get(HF_FEED_URL).mock(
            return_value=httpx.Response(200, text=fixture_text("hf_daily_papers.xml"))
        )
        items = await adapter.fetch_and_transform(config)

    assert [item.id for item in items] == ["hf-paper-2407-00001"]
    item = items[0]
    assert item.source == "Hugging Face Daily Papers"
    assert item.category == "AI Research"
    assert item.metadata["feed_url"] == HF_FEED_URL


def test_hf_daily_papers_transform_preserves_caller_overrides() -> None:
    """Explicit ``source_name`` in the caller config wins over the adapter default."""
    items = HFDailyPapersAdapter().transform(
        fixture_text("hf_daily_papers.xml"),
        {"source_name": "Custom HF", "category": "Research"},
    )
    assert items[0].source == "Custom HF"
    assert items[0].category == "Research"


@pytest.mark.asyncio
async def test_tldr_ai_defaults_apply() -> None:
    """TLDR AI adapter tags entries with the dedicated source name."""
    adapter = TLDRAIAdapter()
    with respx.mock:
        respx.get(TLDR_FEED_URL).mock(
            return_value=httpx.Response(200, text=fixture_text("tldr_ai.xml"))
        )
        items = await adapter.fetch_and_transform({})

    assert [item.id for item in items] == ["tldr-2026-07-16-001"]
    item = items[0]
    assert item.source == "TLDR AI"
    assert item.category == "AI Newsletter"
    assert item.metadata["feed_url"] == TLDR_FEED_URL


@pytest.mark.asyncio
async def test_hacker_news_defaults_apply() -> None:
    """Hacker News adapter tags entries with the dedicated source name."""
    adapter = HackerNewsAdapter()
    with respx.mock:
        respx.get(HN_FEED_URL).mock(
            return_value=httpx.Response(200, text=fixture_text("hackernews.xml"))
        )
        items = await adapter.fetch_and_transform({})

    assert [item.id for item in items] == ["hn-1001"]
    item = items[0]
    assert item.source == "Hacker News"
    assert item.category == "Hacker News"
    assert item.metadata["feed_url"] == HN_FEED_URL


@pytest.mark.asyncio
async def test_last_week_in_ai_defaults_apply() -> None:
    """Last Week in AI adapter tags entries with the dedicated source name."""
    adapter = LastWeekInAIAdapter()
    with respx.mock:
        respx.get(LWIA_FEED_URL).mock(
            return_value=httpx.Response(200, text=fixture_text("last_week_in_ai.xml"))
        )
        items = await adapter.fetch_and_transform({})

    assert [item.id for item in items] == ["lwia-2026-07-13-001"]
    item = items[0]
    assert item.source == "Last Week in AI"
    assert item.category == "AI Newsletter"
    assert item.metadata["feed_url"] == LWIA_FEED_URL


def test_four_new_adapters_are_discovered_with_unique_metadata() -> None:
    """Each new adapter registers a unique metadata.id through discovery."""
    scan_and_register()
    metadata_ids = {metadata.id for metadata in AdapterRegistry.get_instance().list_metadata()}
    assert {"hf_daily_papers", "tldr_ai", "hacker_news", "last_week_in_ai"} <= metadata_ids


@pytest.mark.asyncio
async def test_each_adapter_isolates_network_failure() -> None:
    """A failed fetch returns ``[]`` without bubbling the exception to the caller."""
    for adapter_cls, url in (
        (HFDailyPapersAdapter, HF_FEED_URL),
        (TLDRAIAdapter, TLDR_FEED_URL),
        (HackerNewsAdapter, HN_FEED_URL),
        (LastWeekInAIAdapter, LWIA_FEED_URL),
    ):
        with respx.mock:
            respx.get(url).mock(side_effect=httpx.ConnectError("offline"))
            items = await adapter_cls().fetch_and_transform({})
        assert items == []
