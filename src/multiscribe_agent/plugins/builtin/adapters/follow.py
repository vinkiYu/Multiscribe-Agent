"""Follow OPML import adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

import structlog
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from multiscribe_agent.core.errors import AdapterError
from multiscribe_agent.domain.models import ConfigField, PluginMetadata, UnifiedData
from multiscribe_agent.plugins.base import BaseAdapter

UNKNOWN_PUBLISHED_DATE = "1970-01-01T00:00:00+00:00"
log = structlog.get_logger(__name__)


class FollowAdapter(BaseAdapter):
    """Parse Follow-exported OPML feeds into canonical subscription records."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="follow_opml",
        type="adapter",
        name="Follow OPML Import",
        description="Import RSS and Atom subscriptions from a Follow OPML export.",
        icon="follow",
        config_fields=[
            ConfigField(
                key="opml_path",
                label="OPML file path",
                type="text",
                required=True,
                help_text="Local path to a Follow-exported OPML file.",
            ),
            ConfigField(
                key="source_tag",
                label="Source tag",
                type="text",
                help_text="Optional category for feeds without an OPML category.",
            ),
        ],
    )

    async def fetch(self, config: Mapping[str, object]) -> object:
        """Read one non-empty OPML file without blocking the event loop.

        Args:
            config: Adapter configuration containing ``opml_path``.

        Returns:
            Raw OPML XML text.

        Raises:
            AdapterError: If the local file cannot be read or has no content.
        """
        path = Path(self._required_text(config, "opml_path"))
        try:
            raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
        except FileNotFoundError as exc:
            raise AdapterError("Follow OPML file was not found") from exc
        except UnicodeDecodeError as exc:
            raise AdapterError("Follow OPML file must be UTF-8 text") from exc
        except OSError as exc:
            log.warning("follow_opml_read_failed", error_type=type(exc).__name__)
            raise AdapterError("Follow OPML file could not be read") from exc
        if not raw.strip():
            raise AdapterError("Follow OPML file is empty")
        return raw

    def transform(
        self, raw: object, config: Mapping[str, object] | None = None
    ) -> list[UnifiedData]:
        """Parse valid OPML outlines into Follow subscription records.

        Invalid XML and outline entries without ``xmlUrl`` are intentionally
        isolated as no results so a malformed export cannot break ingestion.
        """
        if not isinstance(raw, str) or not raw.strip():
            return []
        try:
            root = ElementTree.fromstring(raw)
        except (DefusedXmlException, ElementTree.ParseError):
            log.warning("follow_opml_parse_failed", adapter_id=self.metadata.id)
            return []

        source_tag = self._optional_text((config or {}).get("source_tag"))
        items: list[UnifiedData] = []
        for outline in root.iter():
            if self._local_name(outline.tag) != "outline":
                continue
            item = self._to_unified_data(outline.attrib, source_tag)
            if item is not None:
                items.append(item)
        return items

    @staticmethod
    def _to_unified_data(
        attributes: Mapping[str, str], source_tag: str | None
    ) -> UnifiedData | None:
        """Normalize one subscription outline when it carries a feed URL."""
        url = FollowAdapter._optional_text(attributes.get("xmlUrl"))
        if url is None:
            return None
        title = (
            FollowAdapter._optional_text(attributes.get("text"))
            or FollowAdapter._optional_text(attributes.get("title"))
            or url
        )
        description = FollowAdapter._optional_text(attributes.get("description")) or ""
        html_url = FollowAdapter._optional_text(attributes.get("htmlUrl")) or ""
        category = FollowAdapter._optional_text(attributes.get("category")) or source_tag or ""
        return UnifiedData(
            id=f"follow_opml:{url}",
            title=title,
            url=url,
            description=description,
            published_date=UNKNOWN_PUBLISHED_DATE,
            source="follow_opml",
            category=category,
            metadata={"html_url": html_url, "source_tag": source_tag or ""},
        )

    @staticmethod
    def _local_name(tag: str) -> str:
        """Strip an XML namespace prefix from an element tag."""
        return tag.rsplit("}", maxsplit=1)[-1]

    @staticmethod
    def _required_text(config: Mapping[str, object], key: str) -> str:
        """Read one required non-empty text configuration value."""
        value = FollowAdapter._optional_text(config.get(key))
        if value is None:
            raise AdapterError(f"Follow adapter requires config['{key}']")
        return value

    @staticmethod
    def _optional_text(value: object | None) -> str | None:
        """Normalize an optional non-empty text value."""
        return value.strip() if isinstance(value, str) and value.strip() else None
