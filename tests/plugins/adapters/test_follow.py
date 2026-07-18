"""Tests for Follow OPML parsing and file loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from multiscribe_agent.core.errors import AdapterError
from multiscribe_agent.plugins.builtin.adapters.follow import FollowAdapter
from multiscribe_agent.plugins.discovery import scan_and_register
from multiscribe_agent.plugins.registry import AdapterRegistry

SAMPLE_OPML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <body>
    <outline text="Technology">
      <outline text="Hacker News" title="HN"
               xmlUrl="https://hnrss.org/frontpage"
               htmlUrl="https://news.ycombinator.com"
               description="Technology news"/>
      <outline title="Python" xmlUrl="https://example.test/python.xml" category="engineering"/>
    </outline>
  </body>
</opml>
"""


def test_transform_parses_nested_outlines_and_full_metadata() -> None:
    """Nested feed outlines become complete canonical subscription records."""
    result = FollowAdapter().transform(SAMPLE_OPML, {"source_tag": "follow"})

    assert len(result) == 2
    first = result[0]
    assert first.id == "follow_opml:https://hnrss.org/frontpage"
    assert first.title == "Hacker News"
    assert first.source == "follow_opml"
    assert first.description == "Technology news"
    assert first.published_date == "1970-01-01T00:00:00+00:00"
    assert first.metadata == {
        "html_url": "https://news.ycombinator.com",
        "source_tag": "follow",
    }


def test_transform_uses_outline_category_before_source_tag() -> None:
    """An explicit OPML category has precedence over the configured fallback tag."""
    result = FollowAdapter().transform(SAMPLE_OPML, {"source_tag": "follow"})

    assert result[0].category == "follow"
    assert result[1].category == "engineering"


def test_transform_skips_outlines_without_xml_url() -> None:
    """Folder outlines and incomplete feed entries do not create bogus records."""
    raw = '<opml><body><outline text="Folder"/><outline title="No URL"/></body></opml>'

    assert FollowAdapter().transform(raw, {}) == []


def test_transform_returns_empty_for_invalid_empty_or_non_text_payloads() -> None:
    """Malformed exported files remain isolated from the caller's ingestion batch."""
    adapter = FollowAdapter()

    assert adapter.transform("", {}) == []
    assert adapter.transform("<opml>", {}) == []
    assert adapter.transform(123, {}) == []


def test_transform_decodes_xml_attribute_entities() -> None:
    """The XML parser preserves escaped text instead of treating it as markup."""
    raw = '<opml><outline text="AI &amp; ML" xmlUrl="https://example.test/rss"/></opml>'

    result = FollowAdapter().transform(raw, {})

    assert result[0].title == "AI & ML"


def test_transform_falls_back_to_title_when_text_is_missing() -> None:
    """Feed titles use the OPML title attribute when text is unavailable."""
    raw = '<opml><outline title="Fallback title" xmlUrl="https://example.test/rss"/></opml>'

    result = FollowAdapter().transform(raw, {})

    assert result[0].title == "Fallback title"


def test_transform_accepts_namespaced_outline_elements() -> None:
    """Namespaced OPML outlines remain discoverable after XML parsing."""
    raw = (
        '<opml xmlns="https://example.test/opml"><outline text="Namespaced" '
        'xmlUrl="https://example.test/rss"/></opml>'
    )

    result = FollowAdapter().transform(raw, {})

    assert [item.url for item in result] == ["https://example.test/rss"]


def test_transform_rejects_doctype_payloads() -> None:
    """Unsafe XML declarations are rejected rather than expanding external entities."""
    raw = """<!DOCTYPE opml [<!ENTITY value "unsafe">]>
    <opml><outline text="&value;" xmlUrl="https://example.test/rss"/></opml>"""

    assert FollowAdapter().transform(raw, {}) == []


@pytest.mark.asyncio
async def test_fetch_reads_a_local_opml_file(tmp_path: Path) -> None:
    """Fetch asynchronously reads the configured local file and returns XML text."""
    opml_file = tmp_path / "feeds.opml"
    opml_file.write_text(SAMPLE_OPML, encoding="utf-8")

    raw = await FollowAdapter().fetch({"opml_path": str(opml_file)})

    assert raw == SAMPLE_OPML


@pytest.mark.asyncio
async def test_fetch_rejects_missing_empty_and_invalid_config(tmp_path: Path) -> None:
    """Missing path, missing file, and empty files report adapter-domain errors."""
    adapter = FollowAdapter()
    empty_file = tmp_path / "empty.opml"
    empty_file.write_text("", encoding="utf-8")

    with pytest.raises(AdapterError, match="opml_path"):
        await adapter.fetch({})
    with pytest.raises(AdapterError, match="not found"):
        await adapter.fetch({"opml_path": str(tmp_path / "missing.opml")})
    with pytest.raises(AdapterError, match="empty"):
        await adapter.fetch({"opml_path": str(empty_file)})


def test_follow_adapter_is_discovered() -> None:
    """The self-describing adapter appears in standard plugin discovery."""
    result = scan_and_register()

    assert "multiscribe_agent.plugins.builtin.adapters.follow.FollowAdapter" in result.registered
    assert any(item.id == "follow_opml" for item in AdapterRegistry.get_instance().list_metadata())
