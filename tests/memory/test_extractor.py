"""Tests for PreferenceExtractor conversation + merge paths."""

from __future__ import annotations

import json

import pytest

from multiscribe_agent.domain.models import AIMessage, AIResponse
from multiscribe_agent.memory.extractor import PreferenceExtractor
from multiscribe_agent.memory.preference_store import UserPreferences


class StaticTagProvider:
    """Return a fixed tag-classification JSON for the existing history path."""

    async def generate(self, *args, **kwargs) -> AIResponse:
        return AIResponse(content='["llm-tag"]')


class ScriptedConversationProvider:
    """Return a configurable JSON payload from the conversation extraction prompt."""

    def __init__(self, payload: dict[str, object] | str) -> None:
        self._payload = payload

    async def generate(self, *args, **kwargs) -> AIResponse:
        if isinstance(self._payload, str):
            content = self._payload
        else:
            content = json.dumps(self._payload, ensure_ascii=False)
        return AIResponse(content=content)


def test_merge_into_appends_and_dedupes_without_dropping_manual_values() -> None:
    """merge_into preserves existing manual tags and appends delta values."""
    extractor = PreferenceExtractor(None, None, None)  # type: ignore[arg-type]
    preferences = UserPreferences(
        preferred_tags=["agent"],
        block_sources=["noise"],
        push_time="09:00",
        importance_threshold=5,
        blocked_topics=["web3"],
    )
    merged = extractor.merge_into(
        preferences,
        {"preferred_tags": ["RAG", "agent"], "blocked_topics": ["融资"]},
    )
    assert merged.preferred_tags == ["agent", "RAG"]
    assert merged.blocked_topics == ["web3", "融资"]
    assert merged.block_sources == ["noise"]
    assert merged.push_time == "09:00"
    assert merged.importance_threshold == 5


def test_merge_into_respects_max_tag_cap() -> None:
    """Excess delta values are dropped from the tail when the cap is reached."""
    extractor = PreferenceExtractor(None, None, None)  # type: ignore[arg-type]
    preferences = UserPreferences(["a", "b", "c"], [], "09:00", 5)
    merged = extractor.merge_into(preferences, {"preferred_tags": ["d", "e", "f"]}, max_tags=4)
    assert merged.preferred_tags == ["a", "b", "c", "d"]


def test_merge_into_ignores_invalid_delta_shapes() -> None:
    """Non-list or non-string entries are ignored rather than raising."""
    extractor = PreferenceExtractor(None, None, None)  # type: ignore[arg-type]
    preferences = UserPreferences(["agent"], [], "09:00", 5)
    merged = extractor.merge_into(
        preferences,
        {"preferred_tags": "not-a-list", "blocked_topics": [1, None, "ok"]},
    )
    assert merged.preferred_tags == ["agent"]
    assert merged.blocked_topics == ["ok"]


@pytest.mark.asyncio
async def test_extract_from_conversation_without_provider_returns_empty_delta() -> None:
    """No LLM provider means no extraction; manual preferences remain untouched."""
    extractor = PreferenceExtractor(None, None, None)  # type: ignore[arg-type]
    delta = await extractor.extract_from_conversation([AIMessage(role="user", content="hello")])
    assert delta == {}


@pytest.mark.asyncio
async def test_extract_from_conversation_parses_valid_json_delta() -> None:
    """A well-formed JSON object becomes a usable preference delta."""
    extractor = PreferenceExtractor(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        ScriptedConversationProvider(
            {
                "preferred_tags": ["agent", "rag"],
                "block_sources": ["spam.test"],
                "blocked_topics": ["招聘"],
            }
        ),
    )
    delta = await extractor.extract_from_conversation(
        [
            AIMessage(role="user", content="我想看 Agent 框架"),
            AIMessage(role="assistant", content="好的，我会重点关注"),
        ]
    )
    assert delta == {
        "preferred_tags": ["agent", "rag"],
        "block_sources": ["spam.test"],
        "blocked_topics": ["招聘"],
    }


@pytest.mark.asyncio
async def test_extract_from_conversation_handles_invalid_json() -> None:
    """Garbage responses degrade to an empty delta without raising."""
    extractor = PreferenceExtractor(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        ScriptedConversationProvider("not json at all"),
    )
    delta = await extractor.extract_from_conversation([AIMessage(role="user", content="hi")])
    assert delta == {}
