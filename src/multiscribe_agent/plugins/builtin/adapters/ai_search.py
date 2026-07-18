"""LLM-backed adapter that normalizes AI-search responses."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from hashlib import sha256
from typing import TYPE_CHECKING, ClassVar

import structlog

from multiscribe_agent.core.errors import AdapterError, ProviderError
from multiscribe_agent.domain.models import AIMessage, ConfigField, PluginMetadata, UnifiedData
from multiscribe_agent.plugins.base import BaseAdapter

if TYPE_CHECKING:
    from multiscribe_agent.llm.provider import AIProvider

UNKNOWN_PUBLISHED_DATE = "1970-01-01T00:00:00+00:00"
DEFAULT_MAX_ITEMS = 5
DEFAULT_RECENCY_DAYS = 7
MAX_DESCRIPTION_LENGTH = 200
log = structlog.get_logger(__name__)

_PROMPT_TEMPLATES = {
    "perplexity": (
        "You are an AI search assistant. Given the query below, return the top "
        "{max_items} most relevant recent results from the past {recency_days} days.\n"
        "Query: {query}\n\n"
        "Return ONLY a strict JSON array. Every object must include title, url, "
        "description, source, category, and published_date (an ISO 8601 value or null)."
    ),
    "phind": (
        "Search the web for: {query}\n\n"
        "Return the top {max_items} results from the past {recency_days} days as a "
        "strict JSON array. Each object must include title, url, description, source, "
        "category, and published_date. Return no prose or Markdown fences."
    ),
}


class AISearchAdapter(BaseAdapter):
    """Use an injected provider to return structured AI-search results."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="ai_search",
        type="adapter",
        name="AI Search",
        description="Use an AI provider to retrieve structured search results.",
        icon="search",
        config_fields=[
            ConfigField(
                key="provider",
                label="Provider",
                type="select",
                options=["perplexity", "phind", "custom"],
                default="perplexity",
                help_text="Select the Perplexity, Phind, or custom prompt style.",
            ),
            ConfigField(
                key="query",
                label="Query",
                type="text",
                required=True,
                placeholder="latest AI news",
            ),
            ConfigField(
                key="max_items",
                label="Max items",
                type="number",
                default=DEFAULT_MAX_ITEMS,
            ),
            ConfigField(
                key="recency_days",
                label="Recency (days)",
                type="number",
                default=DEFAULT_RECENCY_DAYS,
            ),
            ConfigField(
                key="custom_prompt",
                label="Custom prompt",
                type="textarea",
                help_text="Supports {query}, {max_items}, and {recency_days} variables.",
            ),
        ],
    )

    def __init__(self, provider: AIProvider) -> None:
        """Create the adapter with its provider dependency.

        Args:
            provider: Provider used to generate the structured search response.
        """
        self._provider = provider

    async def fetch(self, config: Mapping[str, object]) -> object:
        """Generate the raw AI-search response for a configured query.

        Args:
            config: Query, provider style, and optional prompt-template settings.

        Returns:
            The provider's raw text response.

        Raises:
            AdapterError: If configuration is invalid or the provider fails.
        """
        query = self._required_text(config, "query")
        provider_key = self._provider_key(config)
        max_items = self._positive_integer(config, "max_items", DEFAULT_MAX_ITEMS)
        recency_days = self._positive_integer(config, "recency_days", DEFAULT_RECENCY_DAYS)
        custom_prompt = self._optional_text(config.get("custom_prompt"))
        prompt = self._build_prompt(provider_key, query, max_items, recency_days, custom_prompt)
        try:
            response = await self._provider.generate(
                messages=[AIMessage(role="user", content=prompt)]
            )
        except ProviderError as exc:
            log.warning(
                "ai_search_provider_failed",
                provider=provider_key,
                error_type=type(exc).__name__,
            )
            raise AdapterError("AI search provider request failed") from exc
        return response.content

    def transform(
        self, raw: object, config: Mapping[str, object] | None = None
    ) -> list[UnifiedData]:
        """Parse the provider JSON response into canonical items.

        Invalid non-string or non-array payloads deliberately become no results so
        malformed model output does not fail an ingestion batch.
        """
        if not isinstance(raw, str):
            return []
        provider_key = self._provider_key(config or {})
        maximum = self._positive_integer(config or {}, "max_items", DEFAULT_MAX_ITEMS)
        query = self._optional_text((config or {}).get("query"))
        results: list[UnifiedData] = []
        for item in self._parse_json_array(raw):
            normalized = self._to_unified_data(item, provider_key, query)
            if normalized is not None:
                results.append(normalized)
            if len(results) >= maximum:
                break
        return results

    @staticmethod
    def _build_prompt(
        provider: str,
        query: str,
        max_items: int,
        recency_days: int,
        custom_prompt: str | None,
    ) -> str:
        """Render the requested provider prompt without evaluating arbitrary input."""
        template = (
            custom_prompt
            if provider == "custom" and custom_prompt
            else _PROMPT_TEMPLATES.get(provider, _PROMPT_TEMPLATES["perplexity"])
        )
        try:
            return template.format(
                query=query,
                max_items=max_items,
                recency_days=recency_days,
            )
        except (KeyError, ValueError) as exc:
            raise AdapterError("custom AI search prompt has invalid template variables") from exc

    @staticmethod
    def _parse_json_array(raw: str) -> list[dict[str, object]]:
        """Extract a JSON array, including an array wrapped in a Markdown fence."""
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE)
        decoded = AISearchAdapter._decode_array(cleaned)
        if decoded is None:
            match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
            decoded = AISearchAdapter._decode_array(match.group(0)) if match else None
        if decoded is None:
            log.warning("ai_search_json_parse_failed", adapter_id=AISearchAdapter.metadata.id)
            return []
        return [entry for entry in decoded if isinstance(entry, dict)]

    @staticmethod
    def _decode_array(payload: str) -> list[object] | None:
        """Decode one candidate JSON array without exposing its content in logs."""
        try:
            decoded: object = json.loads(payload)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, list) else None

    @staticmethod
    def _to_unified_data(
        item: dict[str, object], provider: str, query: str | None
    ) -> UnifiedData | None:
        """Validate one response object and normalize it to the domain contract."""
        title = AISearchAdapter._optional_text(item.get("title"))
        url = AISearchAdapter._optional_text(item.get("url"))
        if title is None or url is None:
            return None
        published_date = AISearchAdapter._optional_text(item.get("published_date"))
        description = AISearchAdapter._optional_text(item.get("description")) or ""
        source_name = AISearchAdapter._optional_text(item.get("source")) or ""
        category = AISearchAdapter._optional_text(item.get("category")) or ""
        author = AISearchAdapter._optional_text(item.get("author"))
        identifier = sha256(f"{provider}\0{url}".encode()).hexdigest()[:16]
        return UnifiedData(
            id=f"ai_search:{provider}:{identifier}",
            title=title,
            url=url,
            description=description[:MAX_DESCRIPTION_LENGTH],
            published_date=published_date or UNKNOWN_PUBLISHED_DATE,
            source=f"ai_search:{provider}",
            category=category,
            author=author,
            metadata={"query": query or "", "provider": provider, "source": source_name},
        )

    @staticmethod
    def _provider_key(config: Mapping[str, object]) -> str:
        """Return a documented provider style, defaulting to Perplexity."""
        provider = AISearchAdapter._optional_text(config.get("provider")) or "perplexity"
        if provider not in {"perplexity", "phind", "custom"}:
            raise AdapterError("AI search provider must be perplexity, phind, or custom")
        return provider

    @staticmethod
    def _required_text(config: Mapping[str, object], key: str) -> str:
        """Read one non-empty text setting."""
        value = AISearchAdapter._optional_text(config.get(key))
        if value is None:
            raise AdapterError(f"AI search config '{key}' is required")
        return value

    @staticmethod
    def _optional_text(value: object | None) -> str | None:
        """Normalize a non-empty string value."""
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _positive_integer(config: Mapping[str, object], key: str, default: int) -> int:
        """Read a positive integer setting or its documented default."""
        value = config.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise AdapterError(f"AI search config '{key}' must be a positive integer")
        return value
