"""Mocked tests for DingTalk bot payloads, signing, and validation."""

from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import unquote_plus

import httpx
import pytest
import respx

import multiscribe_agent.plugins.builtin.publishers.dingtalk as dingtalk_module
from multiscribe_agent.core.errors import PublisherError
from multiscribe_agent.plugins.builtin.publishers.dingtalk import (
    DingTalkPublisher,
    build_signed_url,
    compute_sign,
)
from multiscribe_agent.plugins.discovery import scan_and_register
from multiscribe_agent.plugins.registry import PublisherRegistry


def test_compute_sign_is_hmac_sha256_then_base64_then_url_encoded() -> None:
    """The signing helper follows the documented DingTalk algorithm."""
    timestamp, encoded_sign = compute_sign("SEC123456")
    expected = hmac.new(b"SEC123456", f"{timestamp}\nSEC123456".encode(), hashlib.sha256).digest()

    assert timestamp.isdigit()
    assert base64.b64decode(unquote_plus(encoded_sign)) == expected
    assert not all(character in "0123456789abcdef" for character in encoded_sign.casefold())


def test_build_signed_url_preserves_existing_webhook_query() -> None:
    """Signing parameters append instead of replacing DingTalk's access token."""
    url = build_signed_url(
        "https://oapi.dingtalk.com/robot/send?access_token=token", "1700000000000", "abc%3D"
    )

    assert "access_token=token&timestamp=1700000000000&sign=abc%3D" in url


@pytest.mark.asyncio
async def test_publish_markdown_and_action_card_payloads() -> None:
    """Both documented DingTalk message formats return a successful status."""
    publisher = DingTalkPublisher()
    with respx.mock:
        route = respx.post("https://oapi.dingtalk.com/robot/send").mock(
            return_value=httpx.Response(200, json={"errcode": 0, "msg_id": "m1"})
        )
        markdown = await publisher.publish(
            "AI daily", {"webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=X"}
        )
        card = await publisher.publish(
            "Details",
            {
                "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=X",
                "action_card": True,
                "single_url": "https://example.test",
            },
        )
    await publisher.close()

    assert markdown["msg_id"] == "m1"
    assert card["status"] == "success"
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_publish_with_secret_signs_the_webhook_url() -> None:
    """An optional secret adds the timestamp/sign query parameters to the request."""
    publisher = DingTalkPublisher()
    with respx.mock:
        route = respx.post("https://oapi.dingtalk.com/robot/send").mock(
            return_value=httpx.Response(200, json={"errcode": 0, "msg_id": "m2"})
        )
        await publisher.publish(
            "content",
            {
                "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=X",
                "secret": "SEC123456",
            },
        )
    await publisher.close()

    request_url = str(route.calls[0].request.url)
    assert "timestamp=" in request_url
    assert "sign=" in request_url


@pytest.mark.asyncio
async def test_publish_validates_webhook_and_keyword() -> None:
    """Required webhook and optional keyword protection are enforced locally."""
    publisher = DingTalkPublisher()
    with pytest.raises(PublisherError, match="webhook_url"):
        await publisher.publish("content", {})
    with pytest.raises(PublisherError, match="keyword"):
        await publisher.publish(
            "content",
            {
                "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=X",
                "keyword": "required",
            },
        )
    await publisher.close()


@pytest.mark.asyncio
async def test_business_error_raises_publisher_error() -> None:
    """A non-zero DingTalk errcode is never reported as a success."""
    publisher = DingTalkPublisher()
    with respx.mock:
        respx.post("https://oapi.dingtalk.com/robot/send").mock(
            return_value=httpx.Response(200, json={"errcode": 300001, "errmsg": "invalid"})
        )
        with pytest.raises(PublisherError, match="300001"):
            await publisher.publish(
                "content", {"webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=X"}
            )
    await publisher.close()


@pytest.mark.asyncio
async def test_http_error_never_leaks_the_signing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry exhaustion uses a generic domain error rather than request details."""
    monkeypatch.setattr(dingtalk_module, "RETRY_DELAYS_SECONDS", (0.0,))
    publisher = DingTalkPublisher()
    with respx.mock:
        respx.post("https://oapi.dingtalk.com/robot/send").mock(return_value=httpx.Response(500))
        with pytest.raises(PublisherError) as captured:
            await publisher.publish(
                "content",
                {
                    "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=PUBLIC",
                    "secret": "SECRET_VALUE_99",
                },
            )
    await publisher.close()

    assert "SECRET_VALUE_99" not in str(captured.value)


def test_dingtalk_publisher_is_discovered() -> None:
    """The self-describing publisher is registered by normal discovery."""
    result = scan_and_register()

    assert (
        "multiscribe_agent.plugins.builtin.publishers.dingtalk.DingTalkPublisher"
        in result.registered
    )
    assert any(item.id == "dingtalk" for item in PublisherRegistry.get_instance().list_metadata())
