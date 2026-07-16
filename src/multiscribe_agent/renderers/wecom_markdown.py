"""Render curated digest items as Enterprise WeCom-compatible Markdown."""

from __future__ import annotations

from multiscribe_agent.renderers.feishu_card import DigestItem

MAX_SUMMARY_LENGTH = 300


def render_digest_markdown(
    title: str, items: list[DigestItem], *, footer: str | None = None
) -> str:
    """Return Enterprise WeCom-compatible Markdown for a curated digest.

    WeCom Markdown supports headings, bold text, quotes, and links. It does
    not support tables or base64 image content, so this renderer emits only
    those portable constructs.
    """
    sections = [f"## {title}"]
    for index, item in enumerate(items, start=1):
        sections.append(_item_markdown(index, item))
    if footer is not None and footer.strip():
        sections.append(footer)
    return "\n\n".join(sections)


def render_digest_plain(title: str, items: list[DigestItem]) -> str:
    """Return a plain-text fallback for a curated digest."""
    lines = [title]
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item.title}")
        if item.summary:
            lines.append(_summary(item.summary))
        if item.url:
            lines.append(item.url)
    return "\n".join(lines)


def _item_markdown(index: int, item: DigestItem) -> str:
    """Format one item using only WeCom-supported Markdown constructs."""
    summary = _summary(item.summary)
    details = f"> {summary}" if summary else ">"
    source = f"[{item.source}]({item.url})" if item.url else item.source
    score = f" | Score: {item.score:g}" if item.score is not None else ""
    return f"**{index}. {item.title}**\n{details}\n> {source}{score}"


def _summary(value: str) -> str:
    """Bound summaries so one item cannot consume the whole bot message."""
    if len(value) <= MAX_SUMMARY_LENGTH:
        return value
    return f"{value[: MAX_SUMMARY_LENGTH - 3]}..."
