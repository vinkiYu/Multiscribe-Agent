"""Render a constrained Markdown subset as Xiaohongshu note text."""

from __future__ import annotations

import re


def markdown_to_xhs(markdown: str) -> str:
    """Convert Markdown to Xiaohongshu-friendly plain text.

    Args:
        markdown: Source Markdown content.

    Returns:
        Plain note text retaining readable headings, lists, and quotations.
    """
    lines: list[str] = []
    in_code_block = False
    for line in markdown.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            lines.append("")
        elif in_code_block:
            lines.append(line)
        elif stripped.startswith("# "):
            lines.append(f"[Title] {stripped[2:].strip()}")
        elif stripped.startswith("## "):
            lines.append(f"\n[Section] {stripped[3:].strip()}")
        elif stripped.startswith("### "):
            lines.append(f"\n[Topic] {stripped[4:].strip()}")
        elif stripped.startswith(("- ", "* ")):
            lines.append(f"- {_strip_inline(stripped[2:].strip())}")
        elif re.match(r"^\d+\.\s", stripped):
            lines.append(_strip_inline(stripped))
        elif stripped.startswith(">"):
            lines.append(f"Quote: {_strip_inline(stripped[1:].strip())}")
        elif stripped == "---":
            lines.append("\n---\n")
        elif not stripped:
            lines.append("")
        else:
            lines.append(_strip_inline(stripped))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _strip_inline(text: str) -> str:
    """Remove inline Markdown syntax while preserving visible text."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
