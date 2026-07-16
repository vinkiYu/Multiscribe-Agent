"""Mocked webhook tests for the Feishu publisher."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import httpx
import pytest
import respx

import multiscribe_agent.plugins.builtin.publishers.feishu as feishu_module
from multiscribe_agent.core.errors import PublisherError
from multiscribe_agent.plugins.builtin.publishers.feishu import FeishuPublisher, gen_sign
from multiscribe_agent.plugins.discovery import scan_and_register
from multiscribe_agent.plugins.registry import PublisherRegistry

WEBHOOK = "https://open.feishu.example.test/webhook/token"


def request_payload(request: httpx.Request) -> dict[str, object]:
    """Decode one mocked HTTP request payload for assertions."""
    value = json.loads(request.content)
    assert isinstance(value, dict)
    return value


@pytest.mark.asyncio
async def test_publish_card_without_signature() -> None:
    """A card is wrapped as an interactive message and posted successfully."""
    with respx.mock:
        route = respx.post(WEBHOOK).mock(
            return_value=httpx.Response(200, json={"StatusCode": 0, "StatusMessage": "success"})
        )
        result = await FeishuPublisher().publish(
            {"header": {}, "elements": []}, {"webhook": WEBHOOK}
        )

    assert result == {
        "status": "success",
        "response": {"StatusCode": 0, "StatusMessage": "success"},
    }
    assert request_payload(route.calls[0].request) == {
        "msg_type": "interactive",
        "card": {"header": {}, "elements": []},
    }


@pytest.mark.asyncio
async def test_publish_text_with_correct_feishu_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    """A signed text request carries the documented timestamp and HMAC value."""
    monkeypatch.setattr(feishu_module.time, "time", lambda: 1_700_000_000)
    secret = "test-secret"
    with respx.mock:
        route = respx.post(WEBHOOK).mock(return_value=httpx.Response(200, json={"code": 0}))
        result = await FeishuPublisher().publish("hello", {"webhook": WEBHOOK, "secret": secret})

    expected = hmac.new(b"1700000000\ntest-secret", digestmod=hashlib.sha256).digest()
    assert gen_sign(1_700_000_000, secret) == base64.b64encode(expected).decode("utf-8")
    assert result == {"status": "success", "response": {"code": 0}}
    assert request_payload(route.calls[0].request) == {
        "msg_type": "text",
        "content": {"text": "hello"},
        "timestamp": "1700000000",
        "sign": gen_sign(1_700_000_000, secret),
    }


@pytest.mark.asyncio
async def test_publish_retries_after_server_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Transient failures retry with exponential delays and eventually succeed."""
    delays: list[float] = []

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(feishu_module.asyncio, "sleep", record_delay)
    with respx.mock:
        route = respx.post(WEBHOOK).mock(
            side_effect=[
                httpx.Response(500, json={"code": 1}),
                httpx.Response(500, json={"code": 1}),
                httpx.Response(200, json={"code": 0}),
            ]
        )
        result = await FeishuPublisher().publish("retry", {"webhook": WEBHOOK})

    assert result == {"status": "success", "response": {"code": 0}}
    assert route.call_count == 3
    assert delays == [1.0, 2.0]


@pytest.mark.asyncio
async def test_publish_raises_after_all_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unsuccessful Feishu response becomes a publisher-domain error after retries."""

    async def no_delay(delay: float) -> None:
        del delay

    monkeypatch.setattr(feishu_module.asyncio, "sleep", no_delay)
    with respx.mock:
        route = respx.post(WEBHOOK).mock(return_value=httpx.Response(200, json={"code": 9}))
        with pytest.raises(PublisherError, match="after retries"):
            await FeishuPublisher().publish("failure", {"webhook": WEBHOOK})

    assert route.call_count == 4


def test_feishu_publisher_is_discovered() -> None:
    """Discovery registers the built-in publisher metadata."""
    result = scan_and_register()

    assert (
        "multiscribe_agent.plugins.builtin.publishers.feishu.FeishuPublisher" in result.registered
    )
    assert any(
        metadata.id == "feishu_bot" for metadata in PublisherRegistry.get_instance().list_metadata()
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_real_feishu_webhook_is_manual_only() -> None:
    """Reserve an explicit opt-in test slot for a configured real webhook."""
    pytest.skip("manual e2e requires a configured Feishu webhook and secret")
