"""Tests for the provider-injected AI search adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from multiscribe_agent.core.errors import AdapterError
from multiscribe_agent.domain.models import AIResponse
from multiscribe_agent.plugins.builtin.adapters.ai_search import AISearchAdapter
from multiscribe_agent.plugins.discovery import scan_and_register
from multiscribe_agent.plugins.registry import AdapterRegistry


def _provider(content: str) -> MagicMock:
    """Build a provider double that returns one normalized response."""
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=AIResponse(content=content))
    return provider


@pytest.mark.asyncio
async def test_fetch_returns_raw_provider_text() -> None:
    """The query is rendered into a prompt and returns unmodified provider text."""
    provider = _provider("[]")
    adapter = AISearchAdapter(provider)

    result = await adapter.fetch({"query": "AI news", "provider": "phind"})

    assert result == "[]"
    prompt = provider.generate.await_args.kwargs["messages"][0].content
    assert "AI news" in prompt


@pytest.mark.asyncio
async def test_fetch_requires_a_query() -> None:
    """Empty queries fail at the adapter boundary."""
    with pytest.raises(AdapterError, match="query"):
        await AISearchAdapter(_provider("[]")).fetch({"query": " "})


def test_transform_strips_fence_and_sets_complete_domain_fields() -> None:
    """A fenced JSON array yields a fully populated canonical record."""
    raw = """```json
[{"title":"A","url":"https://example.test/a","description":"desc","source":"example.test","category":"AI","published_date":"2026-07-19"}]
```"""

    result = AISearchAdapter(_provider("[]")).transform(raw, {"query": "test", "provider": "phind"})

    assert len(result) == 1
    item = result[0]
    assert item.id.startswith("ai_search:phind:")
    assert item.source == "ai_search:phind"
    assert item.category == "AI"
    assert item.published_date == "2026-07-19"
    assert item.metadata == {"query": "test", "provider": "phind", "source": "example.test"}


def test_transform_recovers_an_embedded_json_array() -> None:
    """Explanatory text around a JSON array does not prevent normalization."""
    raw = 'Here are results: [{"title":"A","url":"https://example.test/a"}] Thanks.'

    result = AISearchAdapter(_provider("[]")).transform(raw, {})

    assert len(result) == 1
    assert result[0].published_date == "1970-01-01T00:00:00+00:00"


def test_transform_invalid_and_non_array_json_return_no_items() -> None:
    """Malformed model output is isolated from the ingestion batch."""
    adapter = AISearchAdapter(_provider("[]"))

    assert adapter.transform("not JSON", {}) == []
    assert adapter.transform('{"title":"not an array"}', {}) == []


def test_transform_skips_incomplete_items_and_honors_max_items() -> None:
    """Records missing required fields are ignored before applying the configured cap."""
    raw = """[
        {"title":"missing URL"},
        {"title":"first","url":"https://example.test/1"},
        {"title":"second","url":"https://example.test/2"}
    ]"""

    result = AISearchAdapter(_provider("[]")).transform(raw, {"max_items": 1})

    assert [item.title for item in result] == ["first"]


def test_custom_prompt_and_provider_validation() -> None:
    """Custom prompt placeholders are rendered and unknown provider styles fail."""
    adapter = AISearchAdapter(_provider("[]"))

    prompt = adapter._build_prompt("custom", "query", 2, 3, "{query}/{max_items}/{recency_days}")
    assert prompt == "query/2/3"
    with pytest.raises(AdapterError, match="provider"):
        adapter.transform("[]", {"provider": "unknown"})


def test_ai_search_adapter_is_discovered() -> None:
    """The metadata-bearing class participates in normal plugin discovery."""
    result = scan_and_register()

    assert (
        "multiscribe_agent.plugins.builtin.adapters.ai_search.AISearchAdapter" in result.registered
    )
    assert any(item.id == "ai_search" for item in AdapterRegistry.get_instance().list_metadata())
