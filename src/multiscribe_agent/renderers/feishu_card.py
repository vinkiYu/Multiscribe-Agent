"""Render curated digest items as Feishu interactive-card or text content."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DigestItem:
    """One curated item shown in a publishing digest."""

    title: str
    summary: str
    url: str
    source: str
    score: float | None = None


def render_digest_card(
    title: str, items: list[DigestItem], *, footer: str | None = None
) -> dict[str, object]:
    """Return a Feishu interactive-card body for one curated digest.

    Args:
        title: Human-readable digest title.
        items: Curated content entries to display.
        footer: Optional plain-text summary shown beneath the entries.

    Returns:
        A card body suitable for Feishu's ``interactive`` webhook message type.
    """
    elements: list[dict[str, object]] = [
        {
            "tag": "markdown",
            "content": _item_markdown(item),
        }
        for item in items
    ]
    if footer is not None and footer.strip():
        elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": footer}]})
    return {
        "header": {"title": {"tag": "plain_text", "content": title}},
        "elements": elements,
    }


def render_digest_text(title: str, items: list[DigestItem]) -> str:
    """Return a plain-text fallback for destinations without card support.

    Args:
        title: Human-readable digest title.
        items: Curated content entries to display.

    Returns:
        A readable title followed by one markdown-style item per line.
    """
    lines = [title]
    for item in items:
        lines.append(f"- {item.title} ({item.source})")
        if item.summary:
            lines.append(f"  {item.summary}")
        if item.url:
            lines.append(f"  {item.url}")
    return "\n".join(lines)


def _item_markdown(item: DigestItem) -> str:
    """Format one digest entry as a Feishu markdown element."""
    link = f"[{item.title}]({item.url})" if item.url else item.title
    source = f"\n\nSource: {item.source}" if item.source else ""
    score = f" | Score: {item.score:g}" if item.score is not None else ""
    summary = f"\n{item.summary}" if item.summary else ""
    return f"**{link}**{score}{summary}{source}"
