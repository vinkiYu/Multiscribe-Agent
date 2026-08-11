"""Hacker News RSS adapter.

Subclass of :class:`RSSAdapter` that tags items with a dedicated source name
and ``metadata.id`` so the curation pipeline can attribute Hacker News stories
separately from generic RSS feeds. The endpoint serves an RSS 2.0 feed at
``https://news.ycombinator.com/rss``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from multiscribe_agent.domain.models import ConfigField, PluginMetadata, UnifiedData
from multiscribe_agent.plugins.builtin.adapters.rss import RSSAdapter

DEFAULT_FEED_URL = "https://news.ycombinator.com/rss"
DEFAULT_SOURCE_NAME = "Hacker News"


class HackerNewsAdapter(RSSAdapter):
    """Fetch Hacker News front-page RSS entries with a stable source."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="hacker_news",
        type="adapter",
        name="Hacker News",
        description="Fetch Hacker News front-page stories via the official RSS feed.",
        icon="forum",
        config_fields=[
            ConfigField(
                key="rss_url",
                label="Feed URL",
                type="url",
                default=DEFAULT_FEED_URL,
                required=False,
                scope="item",
                help_text="Override the default Hacker News RSS feed URL.",
            ),
            ConfigField(
                key="source_name",
                label="Source name",
                type="text",
                default=DEFAULT_SOURCE_NAME,
                scope="item",
            ),
            ConfigField(
                key="category",
                label="Category",
                type="text",
                default="Hacker News",
                scope="item",
            ),
        ],
    )

    async def fetch_and_transform(self, config: Mapping[str, object]) -> list[UnifiedData]:
        """Apply Hacker News defaults when callers omit URL or label."""
        merged = self._defaults(config)
        return await super().fetch_and_transform(merged)

    def transform(
        self, raw: object, config: Mapping[str, object] | None = None
    ) -> list[UnifiedData]:
        """Apply Hacker News defaults before delegating to ``RSSAdapter``."""
        return super().transform(raw, self._defaults(config))

    @staticmethod
    def _defaults(config: Mapping[str, object] | None) -> dict[str, object]:
        """Fill in defaults while preserving any explicit caller overrides."""
        base: dict[str, object] = {
            "rss_url": DEFAULT_FEED_URL,
            "source_name": DEFAULT_SOURCE_NAME,
            "category": "Hacker News",
        }
        if config:
            base.update(config)
        return base
