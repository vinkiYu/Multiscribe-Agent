"""Persistence boundary for anonymous clicks on the public daily digest."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.dialect import ExplicitDatabaseDialectMixin


class ClickEventRepository(ExplicitDatabaseDialectMixin):
    """Store click events and aggregate their bounded tag signals."""

    async def record(
        self,
        db: Database,
        *,
        digest_date: str,
        item_url: str,
        item_source: str | None,
        item_tags: list[str],
        user_agent: str | None = None,
        referer: str | None = None,
    ) -> None:
        """Persist one click with normalized, de-duplicated tags."""
        tags = _normalize_tags(item_tags)
        await self._execute(
            db,
            """
            INSERT INTO click_events(
                digest_date, item_url, item_source, item_tags, clicked_at,
                user_agent, referer
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                digest_date,
                item_url,
                item_source,
                json.dumps(tags, ensure_ascii=False),
                datetime.now(UTC).isoformat(),
                user_agent,
                referer,
            ),
        )

    async def tag_click_counts(
        self,
        db: Database,
        *,
        since_date: str,
        min_clicks: int = 1,
    ) -> dict[str, int]:
        """Aggregate tags from clicks on or after ``since_date``."""
        if min_clicks < 1:
            raise ValueError("min_clicks must be at least 1")
        rows = await self._fetchall(
            db,
            "SELECT item_tags FROM click_events WHERE clicked_at >= ?",
            (f"{since_date}T00:00:00",),
        )
        counts: dict[str, int] = {}
        for row in rows:
            raw = row.get("item_tags")
            if not isinstance(raw, str):
                continue
            try:
                tags = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(tags, list):
                continue
            for tag in _normalize_tags(tags):
                counts[tag] = counts.get(tag, 0) + 1
        return {tag: count for tag, count in counts.items() if count >= min_clicks}


def _normalize_tags(values: Sequence[object]) -> list[str]:
    """Keep non-empty string tags once per click while preserving their order."""
    return list(
        dict.fromkeys(tag.strip() for tag in values if isinstance(tag, str) and tag.strip())
    )
