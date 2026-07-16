"""Tests for Feishu digest rendering."""

from __future__ import annotations

from multiscribe_agent.renderers.feishu_card import (
    DigestItem,
    render_digest_card,
    render_digest_text,
)


def item(number: int) -> DigestItem:
    """Build one representative digest item."""
    return DigestItem(
        title=f"Item {number}",
        summary=f"Summary {number}",
        url=f"https://example.test/{number}",
        source="Example",
        score=0.5 + number / 10,
    )


def test_render_digest_card_has_header_markdown_items_and_footer() -> None:
    """Each item maps to its own Feishu markdown element."""
    card = render_digest_card("Daily digest", [item(1), item(2)], footer="2 selected")

    assert card["header"] == {"title": {"tag": "plain_text", "content": "Daily digest"}}
    elements = card["elements"]
    assert isinstance(elements, list)
    assert len(elements) == 3
    assert elements[0] == {
        "tag": "markdown",
        "content": (
            "**[Item 1](https://example.test/1)** | Score: 0.6\nSummary 1\n\nSource: Example"
        ),
    }
    assert elements[1]["tag"] == "markdown"
    assert elements[2] == {
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": "2 selected"}],
    }


def test_render_digest_card_handles_empty_and_optional_fields() -> None:
    """Empty feeds produce a valid empty card and optional fields do not add noise."""
    empty = render_digest_card("Empty", [])
    partial = DigestItem(title="Untitled", summary="", url="", source="", score=None)
    one = render_digest_card("One", [partial])

    assert empty == {
        "header": {"title": {"tag": "plain_text", "content": "Empty"}},
        "elements": [],
    }
    assert one["elements"] == [{"tag": "markdown", "content": "**Untitled**"}]


def test_render_digest_text_is_a_readable_fallback() -> None:
    """Plain text includes title, source, summary, and URL for every item."""
    text = render_digest_text("Daily digest", [item(1)])

    assert text == "Daily digest\n- Item 1 (Example)\n  Summary 1\n  https://example.test/1"
