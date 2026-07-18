"""Mocked tests for the WeChat Official Account publisher."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

import multiscribe_agent.plugins.builtin.publishers.wechat as wechat_module
from multiscribe_agent.plugins.builtin.publishers.wechat import WeChatPublisher
from multiscribe_agent.plugins.builtin.publishers.wechat_renderer import markdown_to_wechat_html


def test_renderer_supports_table_code_and_sanitizes_scripts() -> None:
    """Markdown converts to supported HTML without executable markup."""
    html = markdown_to_wechat_html(
        "| a | b |\n|---|---|\n| 1 | 2 |\n\n```python\nprint(1)\n```\n<script>x()</script>"
    )
    assert "<table" in html
    assert "<pre" in html
    assert "<script" not in html


@pytest.mark.asyncio
async def test_publish_creates_draft_and_reuses_token() -> None:
    """Two publishes use one token request and create two drafts."""
    publisher = WeChatPublisher("app-id", "app-secret")
    with respx.mock:
        token = respx.get(f"{wechat_module.WECHAT_API}/cgi-bin/token").mock(
            return_value=httpx.Response(200, json={"access_token": "token", "expires_in": 7200})
        )
        drafts = respx.post(f"{wechat_module.WECHAT_API}/cgi-bin/draft/add").mock(
            return_value=httpx.Response(200, json={"media_id": "draft-id"})
        )
        first = await publisher.publish("**content**", {"title": "Title"})
        second = await publisher.publish("content")
    assert first["draft_id"] == "draft-id"
    assert second["status"] == "draft"
    assert token.call_count == 1
    assert drafts.call_count == 2


@pytest.mark.asyncio
async def test_publish_limits_concurrent_draft_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """The publisher never issues more than three draft requests concurrently."""
    publisher = WeChatPublisher("app-id", "app-secret")
    active = 0
    maximum = 0

    async def fake_token(_: httpx.AsyncClient) -> str:
        return "token"

    async def fake_draft(*_: object) -> str:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0)
        active -= 1
        return "draft-id"

    monkeypatch.setattr(publisher._tokens, "get_token", fake_token)
    monkeypatch.setattr(publisher, "_create_draft", fake_draft)
    await asyncio.gather(*(publisher.publish("content") for _ in range(6)))
    assert maximum == 3
