"""Preference extraction from existing publish-history outcomes."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import structlog

from multiscribe_agent.core.errors import ProviderError
from multiscribe_agent.core.publish_history import PublishHistory
from multiscribe_agent.domain.models import AIMessage, MemoryEntry
from multiscribe_agent.infra.db import Database
from multiscribe_agent.llm.provider import AIProvider

log = structlog.get_logger(__name__)


class PreferenceExtractor:
    """Infer durable interest signals from previously published content."""

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
