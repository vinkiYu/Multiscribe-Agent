"""Mocked webhook tests for the Enterprise WeCom publisher."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

import multiscribe_agent.plugins.builtin.publishers.wecom as wecom_module
from multiscribe_agent.core.errors import PublisherError
from multiscribe_agent.plugins.builtin.publishers.wecom import WeComPublisher
from multiscribe_agent.plugins.discovery import scan_and_register
from multiscribe_agent.plugins.registry import PublisherRegistry

KEY = "group-bot-key"
WEBHOOK = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={KEY}"


def request_payload(request: httpx.Request) -> dict[str, object]:
    """Decode a mocked request JSON body for assertions."""
    payload = json.loads(request.content)
    assert isinstance(payload, dict)
    return payload


@pytest.mark.asyncio
async def test_publish_accepts_full_webhook_and_markdown() -> None:
    """A full URL receives a correctly structured Markdown payload."""
    with respx.mock:
        route = respx.post(WEBHOOK).mock(return_value=httpx.Response(200, json={"errcode": 0}))
        result = await WeComPublisher().publish("## Digest", {"webhook": WEBHOOK})

    assert result == {"status": "success", "response": {"errcode": 0}}
    assert request_payload(route.calls[0].request) == {
        "msgtype": "markdown",
        "markdown": {"content": "## Digest"},
    }


@pytest.mark.asyncio
async def test_publish_accepts_key_only_and_text_fallback() -> None:
    """A bare webhook key is normalized and may explicitly send text."""
    with respx.mock:
        route = respx.post(WEBHOOK).mock(return_value=httpx.Response(200, json={"errcode": 0}))
        result = await WeComPublisher().publish("fallback", {"webhook": KEY, "msgtype": "text"})

    assert result == {"status": "success", "response": {"errcode": 0}}
    assert request_payload(route.calls[0].request) == {
        "msgtype": "text",
        "text": {"content": "fallback"},
    }


@pytest.mark.asyncio
async def test_publish_retries_and_surfaces_wecom_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Server failures retry, while final WeCom errors preserve the service message."""
    delays: list[float] = []

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(wecom_module.asyncio, "sleep", record_delay)
    with respx.mock:
        route = respx.post(WEBHOOK).mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(500),
                httpx.Response(200, json={"errcode": 0, "errmsg": "ok"}),
            ]
        )
        result = await WeComPublisher().publish("retry", {"webhook": KEY})

    assert result == {"status": "success", "response": {"errcode": 0, "errmsg": "ok"}}
    assert route.call_count == 3
    assert delays == [1.0, 2.0]

    async def no_delay(delay: float) -> None:
        del delay

    monkeypatch.setattr(wecom_module.asyncio, "sleep", no_delay)
    with respx.mock:
        route = respx.post(WEBHOOK).mock(
            return_value=httpx.Response(200, json={"errcode": 93000, "errmsg": "invalid webhook"})
        )
        with pytest.raises(PublisherError, match="after retries") as error:
            await WeComPublisher().publish("failure", {"webhook": KEY})

    assert "invalid webhook" in str(error.value.__cause__)
    assert route.call_count == 4


def test_wecom_publisher_is_discovered() -> None:
    """Discovery registers the built-in WeCom publisher metadata."""
    result = scan_and_register()

    assert "multiscribe_agent.plugins.builtin.publishers.wecom.WeComPublisher" in result.registered
    assert any(
        metadata.id == "wecom_bot" for metadata in PublisherRegistry.get_instance().list_metadata()
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_real_wecom_webhook_is_manual_only() -> None:
    """Reserve a separately selected test for a configured real webhook."""
    pytest.skip("manual e2e requires a configured Enterprise WeCom webhook")
