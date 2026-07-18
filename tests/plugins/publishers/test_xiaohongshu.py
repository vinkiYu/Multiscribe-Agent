"""Mocked tests for Xiaohongshu rendering and note delivery."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

import multiscribe_agent.plugins.builtin.publishers.xiaohongshu as xhs_module
from multiscribe_agent.core.errors import PublisherError
from multiscribe_agent.plugins.builtin.publishers.xiaohongshu import XiaohongshuPublisher
from multiscribe_agent.plugins.builtin.publishers.xiaohongshu_renderer import markdown_to_xhs
from multiscribe_agent.plugins.discovery import scan_and_register
from multiscribe_agent.plugins.registry import PublisherRegistry


def test_renderer_preserves_text_and_removes_markdown_markers() -> None:
    """Supported presentation syntax becomes readable Xiaohongshu plain text."""
    result = markdown_to_xhs("# Title\n\n**bold** and *italic*\n- item\n`code`")

    assert "Title" in result
    assert "bold and italic" in result
    assert "- item" in result
    assert "code" in result
    assert "**" not in result
    assert "`" not in result


def test_renderer_retains_code_content_and_collapses_blank_lines() -> None:
    """Code-fence delimiters are removed without losing the code text."""
    result = markdown_to_xhs("```python\nprint('hi')\n```\n\n\n\nnext")

    assert "print('hi')" in result
    assert "```" not in result
    assert "\n\n\n" not in result


@pytest.mark.asyncio
async def test_publish_creates_two_notes_with_one_cached_token() -> None:
    """The credential-isolated token manager reuses a valid access token."""
    xhs_module._XhsTokenManager._tokens.clear()
    publisher = XiaohongshuPublisher()
    with respx.mock:
        token = respx.post(xhs_module.XHS_AUTH_URL).mock(
            return_value=httpx.Response(200, json={"access_token": "token", "expires_in": 7200})
        )
        notes = respx.post(xhs_module.XHS_NOTE_URL).mock(
            return_value=httpx.Response(200, json={"code": 0, "data": {"note_id": "n123"}})
        )
        options = {
            "app_key": "key-one",
            "app_secret": "secret-one",
            "title": "AI Weekly",
            "images": ["https://image.test/1.jpg"],
            "topics": ["AI", "news"],
        }
        first = await publisher.publish("**AI** news", options)
        second = await publisher.publish("More news", options)
    await publisher.close()

    assert first["status"] == "published"
    assert second["note_id"] == "n123"
    assert token.call_count == 1
    assert notes.call_count == 2


@pytest.mark.asyncio
async def test_publish_limits_concurrent_note_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    """No more than three outbound note deliveries run at once."""
    publisher = XiaohongshuPublisher()
    active = 0
    maximum = 0

    async def fake_publish(*_args: object) -> dict[str, object]:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0)
        active -= 1
        return {"status": "published", "note_id": "note", "title": "title"}

    monkeypatch.setattr(publisher, "_publish_with_retries", fake_publish)
    options = {"app_key": "key", "app_secret": "secret", "images": ["https://image.test/a"]}
    await asyncio.gather(*(publisher.publish("content", options) for _ in range(6)))
    await publisher.close()

    assert maximum == 3


@pytest.mark.asyncio
async def test_publish_validates_credentials_and_images() -> None:
    """Missing credentials or image assets fail before any HTTP request."""
    publisher = XiaohongshuPublisher()
    with pytest.raises(PublisherError, match="app_key"):
        await publisher.publish("content", {"images": ["https://image.test/a"]})
    with pytest.raises(PublisherError, match="image"):
        await publisher.publish("content", {"app_key": "key", "app_secret": "secret"})
    await publisher.close()


@pytest.mark.asyncio
async def test_publish_business_error_raises_domain_error() -> None:
    """A non-zero platform code is not treated as a successful publication."""
    xhs_module._XhsTokenManager._tokens.clear()
    publisher = XiaohongshuPublisher()
    with respx.mock:
        respx.post(xhs_module.XHS_AUTH_URL).mock(
            return_value=httpx.Response(200, json={"access_token": "token"})
        )
        respx.post(xhs_module.XHS_NOTE_URL).mock(
            return_value=httpx.Response(200, json={"code": 10001, "msg": "invalid"})
        )
        with pytest.raises(PublisherError, match="10001"):
            await publisher.publish(
                "content",
                {
                    "app_key": "key-two",
                    "app_secret": "secret-two",
                    "images": ["https://image.test/a"],
                },
            )
    await publisher.close()


@pytest.mark.asyncio
async def test_http_failure_does_not_leak_a_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Transport failures include no app secret in the public exception text."""
    xhs_module._XhsTokenManager._tokens.clear()
    monkeypatch.setattr(xhs_module, "RETRY_DELAYS_SECONDS", (0.0,))
    publisher = XiaohongshuPublisher()
    with respx.mock:
        respx.post(xhs_module.XHS_AUTH_URL).mock(return_value=httpx.Response(500))
        with pytest.raises(PublisherError) as captured:
            await publisher.publish(
                "content",
                {
                    "app_key": "public-key",
                    "app_secret": "SECRET_VALUE_42",
                    "images": ["https://image.test/a"],
                },
            )
    await publisher.close()

    assert "SECRET_VALUE_42" not in str(captured.value)


def test_xiaohongshu_publisher_is_discovered() -> None:
    """The publisher remains constructible by standard plugin discovery."""
    result = scan_and_register()

    assert (
        "multiscribe_agent.plugins.builtin.publishers.xiaohongshu.XiaohongshuPublisher"
        in result.registered
    )
    assert any(
        item.id == "xiaohongshu" for item in PublisherRegistry.get_instance().list_metadata()
    )
