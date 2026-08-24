"""TLDR AI RSS adapter.

Subclass of :class:`RSSAdapter` that tags items with a dedicated source name
and ``metadata.id`` so the curation pipeline can attribute TLDR AI newsletter
entries. The endpoint serves an RSS 2.0 feed at
``https://tldr.tech/api/rss/ai``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from multiscribe_agent.domain.models import ConfigField, PluginMetadata, UnifiedData
from multiscribe_agent.plugins.builtin.adapters.rss import RSSAdapter

DEFAULT_FEED_URL = "https://tldr.tech/api/rss/ai"
DEFAULT_SOURCE_NAME = "TLDR AI"


class TLDRAIAdapter(RSSAdapter):
    """Fetch TLDR AI newsletter items with a stable source attribution."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="tldr_ai",
        type="adapter",
        name="TLDR AI",
        description="Fetch TLDR AI newsletter entries about the AI industry.",
        icon="article",
        config_fields=[
            ConfigField(
                key="rss_url",
                label="Feed URL",
                type="url",
                default=DEFAULT_FEED_URL,
                required=False,
                scope="item",
                help_text="Override the default TLDR AI RSS feed URL.",
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
                default="AI Newsletter",
                scope="item",
            ),
        ],
    )

    async def fetch_and_transform(self, config: Mapping[str, object]) -> list[UnifiedData]:
        """Apply TLDR AI defaults when callers omit URL or label."""
        merged = self._defaults(config)
        return await super().fetch_and_transform(merged)

    def transform(
        self, raw: object, config: Mapping[str, object] | None = None
    ) -> list[UnifiedData]:
        """Apply TLDR AI defaults before delegating to ``RSSAdapter``."""
        return super().transform(raw, self._defaults(config))

    @staticmethod
    def _defaults(config: Mapping[str, object] | None) -> dict[str, object]:
        """Fill in defaults while preserving any explicit caller overrides."""
        base: dict[str, object] = {
            "rss_url": DEFAULT_FEED_URL,
            "source_name": DEFAULT_SOURCE_NAME,
            "category": "AI Newsletter",
        }
        if config:
            base.update(config)
        return base
