"""Hugging Face Daily Papers RSS adapter.

Subclass of :class:`RSSAdapter` that tags items with a dedicated source name
and ``metadata.id`` so the curation pipeline can attribute HF Daily Papers
separately from generic RSS feeds. The endpoint serves an RSS 2.0 feed at
``https://huggingface.co/daily-papers/rss.xml``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from multiscribe_agent.domain.models import ConfigField, PluginMetadata, UnifiedData
from multiscribe_agent.plugins.builtin.adapters.rss import RSSAdapter

DEFAULT_FEED_URL = "https://huggingface.co/daily-papers/rss.xml"
DEFAULT_SOURCE_NAME = "Hugging Face Daily Papers"


class HFDailyPapersAdapter(RSSAdapter):
    """Fetch Hugging Face Daily Papers and tag entries with a stable source."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="hf_daily_papers",
        type="adapter",
        name="Hugging Face Daily Papers",
        description="Fetch Hugging Face's curated AI research papers of the day.",
        icon="science",
        config_fields=[
            ConfigField(
                key="rss_url",
                label="Feed URL",
                type="url",
                default=DEFAULT_FEED_URL,
                required=False,
                scope="item",
                help_text="Override the default HF Daily Papers RSS feed URL.",
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
                default="AI Research",
                scope="item",
            ),
        ],
    )

    async def fetch_and_transform(self, config: Mapping[str, object]) -> list[UnifiedData]:
        """Apply the HF Daily Papers defaults when callers omit URL or label."""
        merged = self._defaults(config)
        return await super().fetch_and_transform(merged)

    def transform(
        self, raw: object, config: Mapping[str, object] | None = None
    ) -> list[UnifiedData]:
        """Apply HF Daily Papers defaults before delegating to ``RSSAdapter``."""
        return super().transform(raw, self._defaults(config))

    @staticmethod
    def _defaults(config: Mapping[str, object] | None) -> dict[str, object]:
        """Fill in defaults while preserving any explicit caller overrides."""
        base: dict[str, object] = {
            "rss_url": DEFAULT_FEED_URL,
            "source_name": DEFAULT_SOURCE_NAME,
            "category": "AI Research",
        }
        if config:
            base.update(config)
        return base
