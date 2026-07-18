"""WeChat Official Account draft publisher."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import ClassVar

import httpx
import structlog

from multiscribe_agent.core.errors import PublisherError
from multiscribe_agent.domain.models import ConfigField, PluginMetadata
from multiscribe_agent.plugins.base import BasePublisher
from multiscribe_agent.plugins.builtin.publishers.wechat_renderer import markdown_to_wechat_html

WECHAT_API = "https://api.weixin.qq.com"
REQUEST_TIMEOUT_SECONDS = 30.0
RETRY_DELAYS = (1.0, 2.0, 4.0)
log = structlog.get_logger(__name__)


class _TokenManager:
    """Serialize token refreshes and cache the resulting access token."""

    def __init__(self, app_id: str, app_secret: str) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._token = ""
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def get_token(self, client: httpx.AsyncClient) -> str:
        """Return a valid token, refreshing once when it has expired."""
        async with self._lock:
            if self._token and time.monotonic() < self._expires_at:
                return self._token
            response = await client.get(
                f"{WECHAT_API}/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": self._app_id,
                    "secret": self._app_secret,
                },
            )
            response.raise_for_status()
            body = _json_object(response, "token")
            token = body.get("access_token")
            if not isinstance(token, str) or not token:
                raise PublisherError("WeChat token response did not include access_token")
            expires_in = body.get("expires_in", 7200)
            ttl = expires_in if isinstance(expires_in, int) and expires_in > 200 else 7200
            self._token = token
            self._expires_at = time.monotonic() + ttl - 200
            return token


class WeChatPublisher(BasePublisher):
    """Create WeChat Official Account drafts from Markdown content."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="wechat",
        type="publisher",
        name="WeChat Official Account",
        description="Create a WeChat Official Account article draft.",
        icon="wechat",
        config_fields=[
            ConfigField(key="app_id", label="App ID", type="text", required=True, scope="adapter"),
            ConfigField(
                key="app_secret",
                label="App Secret",
                type="password",
                required=True,
                scope="adapter",
            ),
            ConfigField(
                key="author",
                label="Default author",
                type="text",
                default="Multiscribe",
                scope="adapter",
            ),
        ],
    )

    def __init__(self, app_id: str, app_secret: str, author: str = "Multiscribe") -> None:
        if not app_id.strip() or not app_secret.strip():
            raise ValueError("WeChat app_id and app_secret are required")
        self._author = author.strip() or "Multiscribe"
        self._tokens = _TokenManager(app_id, app_secret)
        self._semaphore = asyncio.Semaphore(3)

    async def publish(
        self, content: object, options: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        """Create one draft using options for title, digest, and thumbnail media id."""
        if not isinstance(content, str):
            raise PublisherError("WeChat content must be Markdown text")
        values = options or {}
        title = _option_text(values, "title", "Multiscribe 精选")
        digest = _option_text(values, "digest", content[:54])
        thumb_media_id = _option_text(values, "thumb_media_id", "")
        async with self._semaphore, httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            for attempt in range(len(RETRY_DELAYS) + 1):
                try:
                    token = await self._tokens.get_token(client)
                    draft_id = await self._create_draft(
                        client, token, title, content, digest, thumb_media_id
                    )
                    return {"status": "draft", "draft_id": draft_id, "title": title}
                except (httpx.HTTPError, PublisherError) as exc:
                    if attempt == len(RETRY_DELAYS):
                        raise PublisherError("WeChat draft creation failed after retries") from exc
                    log.warning(
                        "wechat_publish_retry",
                        attempt=attempt + 1,
                        error_type=type(exc).__name__,
                    )
                    await asyncio.sleep(RETRY_DELAYS[attempt])

    async def _create_draft(
        self,
        client: httpx.AsyncClient,
        token: str,
        title: str,
        content: str,
        digest: str,
        thumb_media_id: str,
    ) -> str:
        """Send WeChat's draft-add request and validate the returned media id."""
        response = await client.post(
            f"{WECHAT_API}/cgi-bin/draft/add",
            params={"access_token": token},
            json={
                "articles": [
                    {
                        "title": title,
                        "author": self._author,
                        "digest": digest,
                        "content": markdown_to_wechat_html(content),
                        "content_source_url": "",
                        "thumb_media_id": thumb_media_id,
                        "need_open_comment": 1,
                        "only_fans_can_comment": 0,
                    }
                ]
            },
        )
        response.raise_for_status()
        body = _json_object(response, "draft")
        if body.get("errcode", 0) != 0:
            raise PublisherError("WeChat draft API returned an error")
        media_id = body.get("media_id")
        if not isinstance(media_id, str) or not media_id:
            raise PublisherError("WeChat draft response did not include media_id")
        return media_id


def _json_object(response: httpx.Response, endpoint: str) -> Mapping[str, object]:
    """Read a JSON response object without logging sensitive request data."""
    try:
        body = response.json()
    except ValueError as exc:
        raise PublisherError(f"WeChat {endpoint} response was not JSON") from exc
    if not isinstance(body, Mapping):
        raise PublisherError(f"WeChat {endpoint} response was not an object")
    return body


def _option_text(values: Mapping[str, object], key: str, default: str) -> str:
    """Return a non-empty text option or its documented default."""
    value = values.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else default
