"""RSS and Atom adapter that normalizes feed entries into ``UnifiedData``."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import ClassVar

import feedparser  # type: ignore[import-untyped]  # feedparser does not publish type stubs.
import httpx
import structlog

from multiscribe_agent.core.errors import AdapterError
from multiscribe_agent.domain.models import ConfigField, PluginMetadata, UnifiedData
from multiscribe_agent.plugins.base import BaseAdapter

REQUEST_TIMEOUT_SECONDS = 30.0
log = structlog.get_logger(__name__)


class RSSAdapter(BaseAdapter):
    """Fetch standard RSS/Atom feeds and transform entries into canonical items."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="rss",
        type="adapter",
        name="RSS subscription",
        description="Fetch standard RSS and Atom feeds.",
        icon="rss_feed",
        config_fields=[
            ConfigField(
                key="rss_url",
                label="Feed URL",
                type="url",
                required=True,
                scope="item",
            ),
            ConfigField(
                key="source_name",
                label="Source name",
                type="text",
                scope="item",
            ),
            ConfigField(key="category", label="Category", type="text", scope="item"),
        ],
    )

    async def fetch(self, config: Mapping[str, object]) -> object:
        """Fetch raw feed XML with a bounded asynchronous HTTP request.

        Raises:
            AdapterError: If the URL is invalid or the feed cannot be fetched.
        """
        url = self._required_string(config, "rss_url")
        proxy_value = config.get("proxy")
        proxy = proxy_value if isinstance(proxy_value, str) and proxy_value else None
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, proxy=proxy) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("rss_fetch_failed", error_type=type(exc).__name__)
            raise AdapterError("RSS feed request failed") from exc
        return response.text

    def transform(
        self, raw: object, config: Mapping[str, object] | None = None
    ) -> list[UnifiedData]:
        """Parse feed XML and normalize valid entries into ``UnifiedData`` items."""
        if not isinstance(raw, str):
            raise AdapterError("RSS feed payload must be text")
        settings = config or {}
        parsed = feedparser.parse(raw)
        feed = self._mapping_value(parsed, "feed")
        entries = self._mapping_value(parsed, "entries")
        feed_title = self._string_value(self._mapping_value(feed, "title")) or "RSS"
        source = self._optional_string(settings.get("source_name")) or feed_title
        category = self._optional_string(settings.get("category")) or feed_title
        if not isinstance(entries, list):
            return []

        items: list[UnifiedData] = []
        for entry in entries:
            item = self._to_unified_data(entry, source, category)
            if item is not None:
                items.append(item)
        return items

    def _to_unified_data(self, entry: object, source: str, category: str) -> UnifiedData | None:
        identifier = self._first_non_empty(
            self._mapping_value(entry, "guid"),
            self._mapping_value(entry, "link"),
            self._mapping_value(entry, "id"),
        )
        if identifier is None:
            log.warning("rss_entry_skipped", reason="missing_id")
            return None
        title = self._string_value(self._mapping_value(entry, "title")) or "(untitled)"
        url = self._string_value(self._mapping_value(entry, "link")) or identifier
        summary = self._string_value(self._mapping_value(entry, "summary")) or ""
        author = self._string_value(self._mapping_value(entry, "author"))
        return UnifiedData(
            id=identifier,
            title=title,
            url=url,
            description=summary[:300],
            published_date=self._published_date(entry),
            source=source,
            category=category,
            author=author,
            metadata={"tags": self._tags(entry)},
        )

    def _published_date(self, entry: object) -> str:
        parsed = self._mapping_value(entry, "published_parsed") or self._mapping_value(
            entry, "updated_parsed"
        )
        normalized = self._normalized_struct_time(parsed)
        if normalized is not None:
            return normalized
        raw_date = self._first_non_empty(
            self._mapping_value(entry, "published"), self._mapping_value(entry, "updated")
        )
        return raw_date or "1970-01-01T00:00:00+00:00"

    @staticmethod
    def _normalized_struct_time(value: object) -> str | None:
        if not isinstance(value, tuple) or len(value) < 6:
            return None
        parts = value[:6]
        if not all(isinstance(part, int) and not isinstance(part, bool) for part in parts):
            return None
        year, month, day, hour, minute, second = (int(part) for part in parts)
        try:
            return datetime(year, month, day, hour, minute, second, tzinfo=UTC).isoformat()
        except ValueError:
            return None

    def _tags(self, entry: object) -> list[str]:
        tags = self._mapping_value(entry, "tags")
        if not isinstance(tags, list):
            return []
        return [
            term
            for tag in tags
            if (term := self._string_value(self._mapping_value(tag, "term"))) is not None
        ]

    @staticmethod
    def _mapping_value(container: object, key: str) -> object | None:
        if isinstance(container, Mapping):
            return container.get(key)
        return None

    @staticmethod
    def _string_value(value: object | None) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None

    def _first_non_empty(self, *values: object | None) -> str | None:
        for value in values:
            normalized = self._string_value(value)
            if normalized is not None:
                return normalized
        return None

    def _required_string(self, config: Mapping[str, object], key: str) -> str:
        value = self._optional_string(config.get(key))
        if value is None:
            raise AdapterError(f"RSS config requires {key}")
        return value

    @staticmethod
    def _optional_string(value: object | None) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None
