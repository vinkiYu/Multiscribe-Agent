"""Enterprise WeCom group-bot publisher with retrying webhook delivery."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import ClassVar

import httpx
import structlog

from multiscribe_agent.core.errors import PublisherError
from multiscribe_agent.domain.models import ConfigField, PluginMetadata
from multiscribe_agent.plugins.base import BasePublisher

WECOM_WEBHOOK_PREFIX = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key="
REQUEST_TIMEOUT_SECONDS = 10.0
RETRY_DELAYS_SECONDS = (1.0, 2.0, 4.0)
log = structlog.get_logger(__name__)


class WeComPublisher(BasePublisher):
    """Publish Markdown or text messages to an Enterprise WeCom group bot."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="wecom_bot",
        type="publisher",
        name="Enterprise WeCom bot",
        description="Send messages to an Enterprise WeCom group through its bot webhook.",
        icon="wecom",
        config_fields=[
            ConfigField(
                key="webhook",
                label="Webhook Key",
                type="text",
                required=True,
                scope="adapter",
                help_text="A full WeCom webhook URL or only its key value.",
            )
        ],
    )

    async def publish(
        self, content: object, options: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        """Post Markdown or plain text to the configured WeCom bot webhook.

        WeCom allows 20 bot messages per minute. Rate limiting belongs to the
        P11 pipeline caller, which owns fan-out frequency and scheduling.
        """
        webhook = self._webhook(options or {})
        payload = self._payload(content, options or {})
        last_error: PublisherError | None = None
        for attempt in range(len(RETRY_DELAYS_SECONDS) + 1):
            try:
                response = await self._post(webhook, payload)
                body = self._response_body(response)
                if body.get("errcode") == 0:
                    return {"status": "success", "response": body}
                message = self._string_value(body.get("errmsg")) or "unknown WeCom error"
                raise PublisherError(f"WeCom webhook returned error: {message}")
            except (httpx.HTTPError, PublisherError) as exc:
                last_error = (
                    exc
                    if isinstance(exc, PublisherError)
                    else PublisherError("WeCom webhook request failed")
                )
                if attempt == len(RETRY_DELAYS_SECONDS):
                    break
                log.warning(
                    "wecom_publish_retry", attempt=attempt + 1, error_type=type(exc).__name__
                )
                await asyncio.sleep(RETRY_DELAYS_SECONDS[attempt])
        raise PublisherError("WeCom publish failed after retries") from last_error

    async def _post(self, webhook: str, payload: dict[str, object]) -> httpx.Response:
        """Send one bounded asynchronous HTTP request."""
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(webhook, json=payload)
            response.raise_for_status()
            return response

    def _webhook(self, options: Mapping[str, object]) -> str:
        """Normalize a full webhook URL or key-only publisher configuration."""
        configured = self._string_value(options.get("webhook"))
        if configured is None:
            raise PublisherError("WeCom webhook must be configured")
        if configured.startswith(("https://", "http://")):
            return configured
        return f"{WECOM_WEBHOOK_PREFIX}{configured}"

    def _payload(self, content: object, options: Mapping[str, object]) -> dict[str, object]:
        """Create the WeCom text or markdown envelope.

        ``options['msgtype']`` permits explicit text fallback; Markdown is the
        default for rendered digest strings.
        """
        if not isinstance(content, str):
            raise PublisherError("WeCom content must be text")
        msgtype = self._string_value(options.get("msgtype")) or "markdown"
        if msgtype not in {"markdown", "text"}:
            raise PublisherError("WeCom msgtype must be markdown or text")
        return {"msgtype": msgtype, msgtype: {"content": content}}

    def _response_body(self, response: httpx.Response) -> Mapping[str, object]:
        """Read a JSON-object response or raise a publisher-domain error."""
        try:
            body = response.json()
        except ValueError as exc:
            raise PublisherError("WeCom webhook response was not JSON") from exc
        if not isinstance(body, Mapping):
            raise PublisherError("WeCom webhook response was not an object")
        return body

    @staticmethod
    def _string_value(value: object | None) -> str | None:
        """Normalize a non-empty configuration or response string."""
        return value.strip() if isinstance(value, str) and value.strip() else None
