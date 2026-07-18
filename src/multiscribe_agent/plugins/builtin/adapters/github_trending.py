"""GitHub Trending adapter that normalizes repositories into ``UnifiedData``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.parse import quote, urlencode

import httpx
import structlog
from selectolax.parser import HTMLParser

from multiscribe_agent.core.errors import AdapterError
from multiscribe_agent.domain.models import ConfigField, PluginMetadata, UnifiedData
from multiscribe_agent.plugins.base import BaseAdapter

BASE_URL = "https://github.com/trending"
REQUEST_TIMEOUT_SECONDS = 30.0
UNKNOWN_PUBLISHED_DATE = "1970-01-01T00:00:00+00:00"
log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _TrendingSettings:
    """Validated runtime settings for one GitHub Trending fetch."""

    language: str
    spoken_language: str
    stars_min: int
    max_items: int


class _HtmlNode(Protocol):
    """Typed subset of a selectolax node used by this adapter."""

    @property
    def attributes(self) -> Mapping[str, str]:
        """Return HTML attributes for this node."""

    def css_first(self, selector: str) -> _HtmlNode | None:
        """Return the first descendant that matches a CSS selector."""

    def text(self, *, separator: str, strip: bool) -> str:
        """Return normalized node text."""


class _HtmlDocument(Protocol):
    """Typed subset of a selectolax HTML document used by this adapter."""

    def css(self, selector: str) -> list[_HtmlNode]:
        """Return nodes matching a CSS selector."""


class GitHubTrendingAdapter(BaseAdapter):
    """Fetch GitHub Trending repositories and normalize the selected entries."""

    metadata = PluginMetadata(
        id="github_trending",
        type="adapter",
        name="GitHub Trending",
        description="Fetch repositories currently trending on GitHub.",
        icon="github",
        config_fields=[
            ConfigField(
                key="language",
                label="Programming language",
                type="text",
                placeholder="python",
                help_text="Optional GitHub language slug, such as python or typescript.",
            ),
            ConfigField(
                key="spoken_language",
                label="Spoken language",
                type="text",
                placeholder="en",
                help_text="Optional GitHub spoken language code, such as en or zh.",
            ),
            ConfigField(
                key="stars_min",
                label="Minimum stars",
                type="number",
                default=0,
                help_text="Exclude repositories with fewer total stars.",
            ),
            ConfigField(
                key="max_items",
                label="Maximum items",
                type="number",
                default=20,
                help_text="Maximum number of normalized repositories to return.",
            ),
        ],
    )

    async def fetch(self, config: Mapping[str, object]) -> object:
        """Fetch GitHub Trending HTML for the supplied adapter configuration.

        Args:
            config: Adapter settings including optional language and spoken-language filters.

        Returns:
            Raw GitHub Trending HTML.

        Raises:
            AdapterError: If configuration is invalid or GitHub cannot be reached.
        """
        settings = self._settings_from_config(config)
        url = self._build_url(settings)
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": "MultiscribeAgent/1.0"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("github_trending_fetch_failed", error_type=type(exc).__name__)
            raise AdapterError("GitHub Trending request failed") from exc
        return response.text

    def transform(
        self, raw: object, config: Mapping[str, object] | None = None
    ) -> list[UnifiedData]:
        """Parse GitHub Trending HTML into canonical repository records.

        Args:
            raw: GitHub Trending HTML returned by :meth:`fetch`.
            config: Optional settings that control filtering and result count.

        Returns:
            Normalized repositories that meet all configured filters.

        Raises:
            AdapterError: If the payload or configuration has an invalid shape.
        """
        if not isinstance(raw, str):
            raise AdapterError("GitHub Trending payload must be text")
        settings = self._settings_from_config(config or {})
        tree = cast(_HtmlDocument, HTMLParser(raw))
        items: list[UnifiedData] = []
        for article in tree.css("article.Box-row"):
            item = self._to_unified_data(article, settings)
            if item is not None:
                items.append(item)
            if len(items) == settings.max_items:
                break
        return items

    @staticmethod
    def _build_url(settings: _TrendingSettings) -> str:
        url = BASE_URL
        if settings.language:
            url = f"{url}/{quote(settings.language, safe='-')}"
        if settings.spoken_language:
            query = urlencode({"spoken_language_code": settings.spoken_language})
            url = f"{url}?{query}"
        return url

    def _to_unified_data(
        self, article: _HtmlNode, settings: _TrendingSettings
    ) -> UnifiedData | None:
        name_node = article.css_first("h2 a")
        if name_node is None:
            return None
        href = name_node.attributes.get("href")
        if not isinstance(href, str):
            return None
        full_name = href.strip("/")
        if not full_name or "/" not in full_name:
            return None

        language = self._node_text(article.css_first('span[itemprop="programmingLanguage"]'))
        if settings.language and language.casefold() != settings.language.casefold():
            return None
        stars = self._stars(article)
        if stars < settings.stars_min:
            return None

        owner, repository = full_name.split("/", maxsplit=1)
        url = f"https://github.com/{full_name}"
        description = self._node_text(article.css_first("p"))
        return UnifiedData(
            id=f"github:{full_name}",
            title=f"[{language or 'Unknown'}] {full_name} ({stars:,} stars)",
            url=url,
            description=description,
            published_date=UNKNOWN_PUBLISHED_DATE,
            source="github_trending",
            category=language or "GitHub Trending",
            author=owner,
            metadata={"language": language, "stars": stars, "repository": repository},
        )

    @staticmethod
    def _node_text(node: _HtmlNode | None) -> str:
        if node is None:
            return ""
        text = node.text(separator=" ", strip=True)
        return text if isinstance(text, str) else ""

    def _stars(self, article: _HtmlNode) -> int:
        star_node = article.css_first('a[href$="/stargazers"]')
        return self._parse_star_count(self._node_text(star_node))

    @staticmethod
    def _parse_star_count(value: str) -> int:
        normalized = value.strip().casefold().replace(",", "")
        multiplier = 1
        if normalized.endswith("k"):
            normalized = normalized[:-1]
            multiplier = 1_000
        elif normalized.endswith("m"):
            normalized = normalized[:-1]
            multiplier = 1_000_000
        try:
            return int(float(normalized) * multiplier)
        except ValueError:
            return 0

    @staticmethod
    def _settings_from_config(config: Mapping[str, object]) -> _TrendingSettings:
        return _TrendingSettings(
            language=GitHubTrendingAdapter._optional_string(config.get("language")),
            spoken_language=GitHubTrendingAdapter._optional_string(config.get("spoken_language")),
            stars_min=GitHubTrendingAdapter._non_negative_integer(config, "stars_min", 0),
            max_items=GitHubTrendingAdapter._non_negative_integer(config, "max_items", 20),
        )

    @staticmethod
    def _optional_string(value: object | None) -> str:
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _non_negative_integer(config: Mapping[str, object], key: str, default: int) -> int:
        value = config.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AdapterError(f"GitHub Trending config '{key}' must be a non-negative integer")
        return value
