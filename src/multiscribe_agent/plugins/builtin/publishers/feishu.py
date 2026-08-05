"""Feishu custom-bot publisher with signing, retries, and response validation."""

from __future__ import annotations

import asyncio  # noqa: F401 - retained as a patch point for retry-delay tests.
import base64
import hashlib
import hmac
import time
from collections.abc import Mapping
from typing import ClassVar

import httpx

from multiscribe_agent.core.errors import PublisherError
from multiscribe_agent.domain.models import ConfigField, PluginMetadata
from multiscribe_agent.plugins.base import BasePublisher

REQUEST_TIMEOUT_SECONDS = 10.0
RETRY_DELAYS_SECONDS = BasePublisher.RETRY_DELAYS_SECONDS


class FeishuPublisher(BasePublisher):
    """Publish interactive cards or text through a Feishu custom-bot webhook."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="feishu_bot",
        type="publisher",
        name="Feishu bot",
        description="Send messages to a Feishu group through a custom-bot webhook.",
        icon="feishu",
        config_fields=[
            ConfigField(
                key="webhook",
                label="Webhook URL",
                type="url",
                required=True,
                scope="adapter",
            ),
            ConfigField(
                key="secret",
                label="Signing secret",
                type="password",
                scope="adapter",
            ),
        ],
    )

    async def publish(
        self, content: object, options: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        """Post card or text content to a configured Feishu webhook.

        Args:
            content: An interactive-card mapping or plain text string.
            options: Publisher configuration containing ``webhook`` and optional ``secret``.

        Returns:
            A serializable success result with Feishu's response body.

        Raises:
            PublisherError: If configuration is invalid or all attempts fail.
        """
        settings = options or {}
        webhook = self._webhook(content, settings)
        secret = self._string_value(settings.get("secret"))
        payload = self._payload(content)
        if secret is not None:
            timestamp = str(int(time.time()))
            payload["timestamp"] = timestamp
            payload["sign"] = gen_sign(int(timestamp), secret)

        async def _send() -> dict[str, object]:
            response = await self._post(webhook, payload)
            response_body = self._response_body(response)
            if not self._is_success(response_body):
                raise PublisherError("Feishu webhook returned an error response")
            return {"status": "success", "response": response_body}

        return await self._send_with_retry(
            _send,
            publisher_name="Feishu",
            retry_delays=RETRY_DELAYS_SECONDS,
        )

    async def _post(self, webhook: str, payload: dict[str, object]) -> httpx.Response:
        """Send one bounded asynchronous webhook request."""
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(webhook, json=payload)
            response.raise_for_status()
            return response

    def _webhook(self, content: object, options: Mapping[str, object]) -> str:
        """Extract a required webhook without retaining it in logs or result data."""
        configured = self._string_value(options.get("webhook"))
        embedded = (
            self._string_value(content.get("webhook")) if isinstance(content, Mapping) else None
        )
        webhook = configured or embedded
        if webhook is None:
            raise PublisherError("Feishu webhook must be configured")
        return webhook

    def _payload(self, content: object) -> dict[str, object]:
        """Wrap supported content in the Feishu webhook message envelope."""
        if isinstance(content, str):
            return {"msg_type": "text", "content": {"text": content}}
        if isinstance(content, Mapping):
            card = {key: value for key, value in content.items() if key != "webhook"}
            return {"msg_type": "interactive", "card": card}
        raise PublisherError("Feishu content must be a card mapping or text string")

    def _response_body(self, response: httpx.Response) -> Mapping[str, object]:
        """Return a JSON object response or raise a publisher-domain error."""
        try:
            body = response.json()
        except ValueError as exc:
            raise PublisherError("Feishu webhook response was not JSON") from exc
        if not isinstance(body, Mapping):
            raise PublisherError("Feishu webhook response was not an object")
        return body

    @staticmethod
    def _is_success(body: Mapping[str, object]) -> bool:
        """Recognize documented Feishu response success conventions."""
        return body.get("StatusCode") == 0 or body.get("code") == 0

    @staticmethod
    def _string_value(value: object | None) -> str | None:
        """Normalize a non-empty configuration string."""
        return value.strip() if isinstance(value, str) and value.strip() else None


def gen_sign(timestamp: int, secret: str) -> str:
    """Generate Feishu's base64-encoded HMAC-SHA256 webhook signature."""
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")
