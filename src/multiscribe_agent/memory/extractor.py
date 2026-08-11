"""Preference extraction from publish history and free-form conversation."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import structlog

from multiscribe_agent.core.errors import ProviderError
from multiscribe_agent.core.publish_history import PublishHistory
from multiscribe_agent.domain.models import AIMessage, MemoryEntry
from multiscribe_agent.infra.db import Database
from multiscribe_agent.llm.provider import AIProvider
from multiscribe_agent.memory.preference_store import UserPreferences

log = structlog.get_logger(__name__)

MAX_CONVERSATION_DELTA_TAGS = 20
_CONVERSATION_PROMPT = (
    "分析以下用户与 AI 的对话，提取稳定的内容偏好。"
    "返回严格 JSON 对象，包含以下可选字段："
    "preferred_tags（关注主题，字符串数组）"
    "block_sources（不想看的来源，字符串数组）"
    "blocked_topics（不想看的主题，字符串数组）"
    "每项最多 5 个，缺失则省略字段。"
    "\n对话：\n{messages}"
)


class PreferenceExtractor:
    """Infer durable interest signals from history and conversations."""

    def __init__(
        self,
        db: Database,
        publish_history: PublishHistory,
        llm_provider: AIProvider | None = None,
    ) -> None:
        """Bind the existing history service to the application database."""
        self._db = db
        self._publish_history = publish_history
        self._llm_provider = llm_provider

    async def extract_from_history(self, days: int = 30, top_n: int = 100) -> list[MemoryEntry]:
        """Read recent history and create one tagged memory per selected record."""
        since = datetime.now(UTC) - timedelta(days=max(1, days))
        records = await self._publish_history.query(
            self._db, from_date=since, limit=max(1, min(top_n, 200))
        )
        frequencies = Counter(record.adapter_name or record.publisher_id for record in records)
        entries: list[MemoryEntry] = []
        for record in records:
            source = record.adapter_name or record.publisher_id
            title_terms = [word.casefold() for word in record.title.split() if len(word) > 2][:3]
            tags = await self._classify_tags(
                record.content_preview or record.title, [source, *title_terms]
            )
            entries.append(
                MemoryEntry(
                    id=str(uuid4()),
                    content=record.content_preview or record.title,
                    importance=min(10, max(1, frequencies[source])),
                    tags=tags,
                    created_at=int(record.published_at.timestamp()),
                    metadata={
                        "source": source,
                        "title": record.title,
                        "publish_record_id": record.id,
                        "category_id": "publish-history",
                    },
                )
            )
        return entries

    async def extract_from_conversation(self, messages: Sequence[AIMessage]) -> dict[str, object]:
        """Return a preference delta parsed from a user/assistant conversation."""
        if self._llm_provider is None:
            log.info("memory_conversation_extraction_skipped_no_provider")
            return {}
        if not messages:
            return {}
        rendered = "\n".join(f"{msg.role}: {msg.content}" for msg in messages)
        try:
            response = await self._llm_provider.generate(
                [AIMessage(role="user", content=_CONVERSATION_PROMPT.format(messages=rendered))]
            )
        except (ProviderError, RuntimeError, ValueError) as exc:
            log.warning(
                "memory_conversation_extraction_failed",
                error_type=type(exc).__name__,
            )
            return {}
        return _parse_conversation_delta(response.content)

    def merge_into(
        self,
        preferences: UserPreferences,
        delta: dict[str, object],
        *,
        max_tags: int = MAX_CONVERSATION_DELTA_TAGS,
    ) -> UserPreferences:
        """Fold one conversation delta into existing preferences without overwriting manual fields."""
        if not delta:
            return preferences
        preferred_tags = _merge_list(
            preferences.preferred_tags, delta.get("preferred_tags"), max_tags
        )
        block_sources = _merge_list(preferences.block_sources, delta.get("block_sources"), max_tags)
        blocked_topics = _merge_list(
            preferences.blocked_topics, delta.get("blocked_topics"), max_tags
        )
        return UserPreferences(
            preferred_tags=preferred_tags,
            block_sources=block_sources,
            push_time=preferences.push_time,
            importance_threshold=preferences.importance_threshold,
            blocked_topics=blocked_topics,
        )

    async def _classify_tags(self, content: str, fallback_tags: list[str]) -> list[str]:
        """Augment deterministic tags with a best-effort, JSON-only LLM classification."""
        fallback = list(dict.fromkeys(fallback_tags))
        if self._llm_provider is None:
            return fallback
        try:
            response = await self._llm_provider.generate(
                [
                    AIMessage(
                        role="user",
                        content=(
                            "Return a JSON array of at most five concise topic tags "
                            "for this content. "
                            f"Content: {content}"
                        ),
                    )
                ]
            )
            value = json.loads(response.content)
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError("LLM tags must be a JSON string array")
            return list(dict.fromkeys([*fallback, *value]))[:8]
        except (json.JSONDecodeError, ProviderError, ValueError) as exc:
            log.warning("memory_tag_classification_failed", error_type=type(exc).__name__)
            return fallback


def _parse_conversation_delta(content: str) -> dict[str, object]:
    """Parse a JSON delta payload from the conversation extraction prompt."""
    if not content or not content.strip():
        return {}
    try:
        decoded = json.loads(content)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    return decoded


def _merge_list(existing: list[str], candidate: object, max_items: int) -> list[str]:
    """Append normalized candidate strings to the existing list, deduplicated and bounded."""
    if not isinstance(candidate, list):
        return list(existing)
    cleaned: list[str] = []
    for item in candidate:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if value:
            cleaned.append(value)
    merged = list(dict.fromkeys([*existing, *cleaned]))
    return merged[:max_items]
