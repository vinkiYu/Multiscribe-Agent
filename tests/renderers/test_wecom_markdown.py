"""Tests for Enterprise WeCom Markdown rendering."""

from __future__ import annotations

from multiscribe_agent.renderers.feishu_card import DigestItem
from multiscribe_agent.renderers.wecom_markdown import (
    MAX_SUMMARY_LENGTH,
    render_digest_markdown,
    render_digest_plain,
)


def item(number: int, summary: str = "Summary") -> DigestItem:
    """Build one representative curated digest item."""
    return DigestItem(
        title=f"Item {number}",
        summary=summary,
        url=f"https://example.test/{number}",
        source="Example",
        score=8.5,
    )


def test_render_digest_markdown_uses_supported_heading_quote_and_links() -> None:
    """One item uses only portable WeCom Markdown syntax."""
    rendered = render_digest_markdown("Daily digest", [item(1)], footer="1 selected")

    assert rendered == (
        "## Daily digest\n\n**1. Item 1**\n> Summary\n> [Example](https://example.test/1)"
        " | Score: 8.5\n\n1 selected"
    )
    assert "base64" not in rendered
    assert "| ---" not in rendered


def test_render_digest_markdown_handles_empty_multiple_and_long_summaries() -> None:
    """Empty feeds, ordinal numbering, and summary boundaries are deterministic."""
    long_summary = "x" * (MAX_SUMMARY_LENGTH + 1)

    assert render_digest_markdown("Empty", []) == "## Empty"
    rendered = render_digest_markdown("Many", [item(1), item(2, long_summary)])
    assert "**1. Item 1**" in rendered
    assert "**2. Item 2**" in rendered
    assert f"> {'x' * (MAX_SUMMARY_LENGTH - 3)}..." in rendered


def test_render_digest_plain_is_readable_fallback() -> None:
    """Plain text preserves the title and every item's main fields."""
    assert render_digest_plain("Daily digest", [item(1)]) == (
        "Daily digest\n1. Item 1\nSummary\nhttps://example.test/1"
    )
