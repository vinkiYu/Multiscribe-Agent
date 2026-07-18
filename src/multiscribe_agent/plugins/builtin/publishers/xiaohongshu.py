"""Xiaohongshu image-text note publisher."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

import httpx
import structlog

from multiscribe_agent.core.errors import PublisherError
from multiscribe_agent.domain.models import ConfigField, PluginMetadata
from multiscribe_agent.plugins.base import BasePublisher
from multiscribe_agent.plugins.builtin.publishers.xiaohongshu_renderer import markdown_to_xhs

REQUEST_TIMEOUT_SECONDS = 30.0
XHS_AUTH_URL = "https://open-api.xiaohongshu.com/oauth/access_token"
XHS_NOTE_URL = "https://open-api.xiaohongshu.com/api/note/create"
SEMAPHORE_LIMIT = 3
TOKEN_REFRESH_BUFFER_SECONDS = 200
DEFAULT_TOKEN_TTL_SECONDS = 7200
RETRY_DELAYS_SECONDS = (1.0, 2.0, 4.0)
log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _CachedToken:
    """A token and its monotonic refresh deadline."""

    value: str
    expires_at: float


class _XhsTokenManager:
    """Process-wide credential-isolated access-token cache."""

    _lock: ClassVar[asyncio.Lock | None] = None
    _tokens: ClassVar[dict[str, _CachedToken]] = {}

    @classmethod
    async def get_token(cls, client: httpx.AsyncClient, app_key: str, app_secret: str) -> str:
        """Return a non-expired token, serializing refreshes across publishers."""
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        cache_key = hashlib.sha256(f"{app_key}\0{app_secret}".encode()).hexdigest()
        async with cls._lock:
            cached = cls._tokens.get(cache_key)
            if cached is not None and time.monotonic() < cached.expires_at:
                return cached.value
            token, ttl = await cls._fetch(client, app_key, app_secret)
            cls._tokens[cache_key] = _CachedToken(
                value=token,
                expires_at=time.monotonic() + max(1, ttl - TOKEN_REFRESH_BUFFER_SECONDS),
            )
            return token

    @staticmethod
    async def _fetch(client: httpx.AsyncClient, app_key: str, app_secret: str) -> tuple[str, int]:
        """Request one token without exposing credentials in errors or logs."""
        response = await client.post(
            XHS_AUTH_URL,
            json={
                "app_key": app_key,
                "app_secret": app_secret,
                "grant_type": "client_credential",
            },
        )
        response.raise_for_status()
        body = _json_object(response, "token")
        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            raise PublisherError("Xiaohongshu token response did not include access_token")
        expires_in = body.get("expires_in", DEFAULT_TOKEN_TTL_SECONDS)
        ttl = (
            expires_in
            if isinstance(expires_in, int) and expires_in > 0
            else DEFAULT_TOKEN_TTL_SECONDS
        )
        return token, ttl


class XiaohongshuPublisher(BasePublisher):
    """Publish image-text notes to the Xiaohongshu open platform."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="xiaohongshu",
        type="publisher",
        name="Xiaohongshu Note",
        description="Publish image-text notes to Xiaohongshu's open platform.",
        icon="xiaohongshu",
        config_fields=[
            ConfigField(key="app_key", label="App Key", type="text", required=True),
            ConfigField(key="app_secret", label="App Secret", type="password", required=True),
            ConfigField(
                key="default_title",
                label="Default Title",
                type="text",
                default="Multiscribe精选",
            ),
            ConfigField(key="title", label="Title", type="text", scope="item"),
            ConfigField(key="images", label="Images", type="textarea", required=True, scope="item"),
            ConfigField(key="topics", label="Topics", type="textarea", scope="item"),
        ],
    )

    def __init__(self) -> None:
        """Create a discovery-compatible publisher with no credentials retained."""
        self._semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
        self._client: httpx.AsyncClient | None = None

    async def publish(
        self, content: object, options: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        """Publish Markdown content as one image-text note.

        Raises:
            PublisherError: If options, a platform response, or delivery is invalid.
        """
        if not isinstance(content, str):
            raise PublisherError("Xiaohongshu content must be Markdown text")
        settings = options or {}
        app_key = self._required_text(settings, "app_key")
        app_secret = self._required_text(settings, "app_secret")
        title = self._optional_text(settings.get("title")) or self._default_title(settings)
        images = self._images(settings.get("images"))
        description = self._compose_description(content, settings.get("topics"))
        async with self._semaphore:
            client = await self._get_client()
            return await self._publish_with_retries(
                client, app_key, app_secret, title, description, images
            )

    async def _publish_with_retries(
        self,
        client: httpx.AsyncClient,
        app_key: str,
        app_secret: str,
        title: str,
        description: str,
        images: list[str],
    ) -> dict[str, object]:
        """Retry only transport failures; business rejections are not retriable."""
        for attempt in range(len(RETRY_DELAYS_SECONDS) + 1):
            try:
                token = await _XhsTokenManager.get_token(client, app_key, app_secret)
                note_id = await self._create_note(client, token, title, description, images)
                return {"status": "published", "note_id": note_id, "title": title}
            except httpx.HTTPError as exc:
                if attempt == len(RETRY_DELAYS_SECONDS):
                    raise PublisherError("Xiaohongshu note request failed after retries") from exc
                log.warning(
                    "xiaohongshu_publish_retry",
                    attempt=attempt + 1,
                    error_type=type(exc).__name__,
                )
                await asyncio.sleep(RETRY_DELAYS_SECONDS[attempt])
        raise PublisherError("Xiaohongshu note request exited unexpectedly")

    async def _create_note(
        self,
        client: httpx.AsyncClient,
        token: str,
        title: str,
        description: str,
        images: list[str],
    ) -> str:
        """Submit the note and validate the platform business response."""
        response = await client.post(
            XHS_NOTE_URL,
            headers={"Authorization": f"Bearer {token}"},
            json={"title": title, "desc": description, "images": images, "type": "normal"},
        )
        response.raise_for_status()
        body = _json_object(response, "note")
        if body.get("code", 0) != 0:
            raise PublisherError(f"Xiaohongshu note API returned error code {body.get('code')}")
        payload = body.get("data")
        note_id = payload.get("note_id") if isinstance(payload, Mapping) else None
        if not isinstance(note_id, str) or not note_id:
            raise PublisherError("Xiaohongshu note response did not include note_id")
        return note_id

    async def _get_client(self) -> httpx.AsyncClient:
        """Reuse one bounded asynchronous HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
        return self._client

    @staticmethod
    def _compose_description(content: str, topics: object | None) -> str:
        """Render Markdown and append validated Xiaohongshu topic tags."""
        description = markdown_to_xhs(content)
        if not isinstance(topics, list):
            return description
        tags = [
            f"#{topic.strip()}#" for topic in topics if isinstance(topic, str) and topic.strip()
        ]
        return f"{description}\n\n{' '.join(tags)}" if tags else description

    @staticmethod
    def _images(value: object | None) -> list[str]:
        """Validate that at least one non-empty image reference is supplied."""
        if not isinstance(value, list):
            raise PublisherError("Xiaohongshu note requires options['images']")
        images = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        if not images:
            raise PublisherError("Xiaohongshu note requires at least one image")
        return images

    @staticmethod
    def _default_title(settings: Mapping[str, object]) -> str:
        """Resolve a non-empty optional configured title."""
        return (
            XiaohongshuPublisher._optional_text(settings.get("default_title")) or "Multiscribe精选"
        )

    @staticmethod
    def _required_text(settings: Mapping[str, object], key: str) -> str:
        """Read a required option without including its value in an error."""
        value = XiaohongshuPublisher._optional_text(settings.get(key))
        if value is None:
            raise PublisherError(f"Xiaohongshu publisher requires options['{key}']")
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


def _json_object(response: httpx.Response, endpoint: str) -> Mapping[str, object]:
    """Read a JSON-object response without logging request or credential data."""
    try:
        body = response.json()
    except ValueError as exc:
        raise PublisherError(f"Xiaohongshu {endpoint} response was not JSON") from exc
    if not isinstance(body, Mapping):
        raise PublisherError(f"Xiaohongshu {endpoint} response was not an object")
    return body
