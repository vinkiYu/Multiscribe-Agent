"""Markdown rendering constrained to the HTML subset accepted by WeChat drafts."""

from __future__ import annotations

import re

from markdown import Markdown  # type: ignore[import-untyped]  # Package has no inline stubs.


def markdown_to_wechat_html(value: str) -> str:
    """Render Markdown into sanitized WeChat-compatible HTML."""
    html = Markdown(extensions=["extra", "nl2br"]).convert(value)
    html = re.sub(
        r"<(script|style|iframe|form|input)\b[^>]*>.*?</\1>",
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    html = re.sub(r"\s+on\w+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", "", html)
    html = html.replace(
        "<pre><code>",
        '<pre style="background:#f6f8fa;padding:16px;overflow-x:auto"><code>',
    )
    html = html.replace("<table>", '<table style="border-collapse:collapse;width:100%">')
    html = html.replace("<th>", '<th style="border:1px solid #ddd;padding:8px">')
    html = html.replace("<td>", '<td style="border:1px solid #ddd;padding:8px">')
    return html
