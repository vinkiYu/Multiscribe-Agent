"""DingTalk custom-bot publisher with optional HMAC signing."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import time
from collections.abc import Mapping
from typing import ClassVar
from urllib.parse import quote_plus

import httpx
import structlog

from multiscribe_agent.core.errors import PublisherError
from multiscribe_agent.domain.models import ConfigField, PluginMetadata
from multiscribe_agent.plugins.base import BasePublisher

REQUEST_TIMEOUT_SECONDS = 20.0
SEMAPHORE_LIMIT = 3
RETRY_DELAYS_SECONDS = (1.0, 2.0, 4.0)
log = structlog.get_logger(__name__)


def compute_sign(secret: str) -> tuple[str, str]:
    """Create DingTalk's timestamp and encoded HMAC-SHA256 signature."""
    timestamp = str(int(time.time() * 1000))
    signing_value = f"{timestamp}\n{secret}"
    digest = hmac.new(
        secret.encode("utf-8"),
        signing_value.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return timestamp, quote_plus(base64.b64encode(digest).decode("utf-8"))


def build_signed_url(webhook: str, timestamp: str, sign: str) -> str:
    """Append a DingTalk timestamp and already URL-encoded signature."""
    separator = "&" if "?" in webhook else "?"
    return f"{webhook}{separator}timestamp={timestamp}&sign={sign}"


class DingTalkPublisher(BasePublisher):
    """Send Markdown or ActionCard messages to a DingTalk custom bot."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="dingtalk",
        type="publisher",
        name="DingTalk Bot",
        description="Send Markdown or ActionCard messages to a DingTalk custom bot.",
        icon="dingtalk",
        config_fields=[
            ConfigField(key="webhook_url", label="Webhook URL", type="url", required=True),
            ConfigField(key="secret", label="Signing Secret", type="password"),
            ConfigField(key="keyword", label="Keyword", type="text"),
            ConfigField(key="title", label="Title", type="text", scope="item"),
            ConfigField(key="action_card", label="ActionCard", type="boolean", scope="item"),
            ConfigField(key="single_url", label="Action URL", type="url", scope="item"),
            ConfigField(key="single_title", label="Action title", type="text", scope="item"),
        ],
    )

    def __init__(self) -> None:
        """Create a discovery-compatible publisher with no credential state."""
        self._semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
        self._client: httpx.AsyncClient | None = None

    async def publish(
        self, content: object, options: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        """Deliver a DingTalk Markdown or ActionCard message.

        Raises:
            PublisherError: If options, keyword validation, or delivery fails.
        """
        if not isinstance(content, str):
            raise PublisherError("DingTalk content must be text")
        settings = options or {}
        webhook = self._required_text(settings, "webhook_url")
        keyword = self._optional_text(settings.get("keyword"))
        if keyword is not None and keyword not in content:
            raise PublisherError("DingTalk message must contain the configured keyword")
        secret = self._optional_text(settings.get("secret"))
        title = self._optional_text(settings.get("title")) or "Multiscribe 推送"
        action_card = settings.get("action_card", False)
        if not isinstance(action_card, bool):
            raise PublisherError("DingTalk option 'action_card' must be a boolean")
        payload = self._payload(
            title=title,
            text=content,
            action_card=action_card,
            single_url=self._optional_text(settings.get("single_url")),
            single_title=self._optional_text(settings.get("single_title")) or "查看详情",
        )
        url = self._signed_url(webhook, secret)
        async with self._semaphore:
            client = await self._get_client()
            return await self._publish_with_retries(client, url, payload, title)

    async def _publish_with_retries(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: dict[str, object],
        title: str,
    ) -> dict[str, object]:
        """Retry transport failures while avoiding sensitive request logging."""
        for attempt in range(len(RETRY_DELAYS_SECONDS) + 1):
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                body = _json_object(response)
            except httpx.HTTPError as exc:
                if attempt == len(RETRY_DELAYS_SECONDS):
                    raise PublisherError("DingTalk webhook request failed after retries") from exc
                log.warning(
                    "dingtalk_publish_retry",
                    attempt=attempt + 1,
                    error_type=type(exc).__name__,
                )
                await asyncio.sleep(RETRY_DELAYS_SECONDS[attempt])
                continue
            if body.get("errcode", 0) != 0:
                raise PublisherError(f"DingTalk webhook returned errcode={body.get('errcode')}")
            message_id = body.get("msg_id")
            return {
                "status": "success",
                "msg_id": message_id if isinstance(message_id, str) else "",
                "title": title,
            }
        raise PublisherError("DingTalk webhook request exited unexpectedly")

    @staticmethod
    def _payload(
        *,
        title: str,
        text: str,
        action_card: bool,
        single_url: str | None,
        single_title: str,
    ) -> dict[str, object]:
        """Build DingTalk's documented Markdown or single-action card payload."""
        if not action_card:
            return {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
        card: dict[str, object] = {
            "title": title,
            "text": text,
            "singleTitle": single_title,
            "btnOrientation": "0",
        }
        if single_url is not None:
            card["singleURL"] = single_url
        return {"msgtype": "actionCard", "actionCard": card}

    @staticmethod
    def _signed_url(webhook: str, secret: str | None) -> str:
        """Apply optional DingTalk signing to the outbound webhook URL."""
        if secret is None:
            return webhook
        timestamp, sign = compute_sign(secret)
        return build_signed_url(webhook, timestamp, sign)

    async def _get_client(self) -> httpx.AsyncClient:
        """Reuse one bounded asynchronous HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
        return self._client

    @staticmethod
    def _required_text(settings: Mapping[str, object], key: str) -> str:
        """Read a required string option without echoing its value."""
        value = DingTalkPublisher._optional_text(settings.get(key))
        if value is None:
            raise PublisherError(f"DingTalk publisher requires options['{key}']")
        return value

    @staticmethod
    def _optional_text(value: object | None) -> str | None:
        """Normalize an optional text option."""
        return value.strip() if isinstance(value, str) and value.strip() else None

    async def close(self) -> None:
        """Close the reusable HTTP client when the publisher is discarded."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def _json_object(response: httpx.Response) -> Mapping[str, object]:
    """Read a DingTalk JSON response without exposing webhook configuration."""
    try:
        body = response.json()
    except ValueError as exc:
        raise PublisherError("DingTalk webhook response was not JSON") from exc
    if not isinstance(body, Mapping):
        raise PublisherError("DingTalk webhook response was not an object")
    return body
