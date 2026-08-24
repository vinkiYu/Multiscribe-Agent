"""Random candidate-pool collector promoted from scripts/sample_curation_dataset.py."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlparse


class SourceRow(TypedDict):
    """Small, serializable projection of one source_data row."""

    id: str
    title: str
    description: str
    url: str
    source: str
    category: str


# 完全排除的源(非 AI 资讯),与 scripts/sample_curation_dataset.py 保持一致。
EXCLUDED_SOURCES = {"The GitHub Blog", "Artificial Intelligence", "AI"}
SHORT_DESCRIPTION_SOURCES = (
    "TLDR AI",
    "Hugging Face Daily Papers",
    "Hacker News",
    "Last Week in AI",
)


class RandomPoolCollector:
    """Build candidate pools of ten rows with minimal cross-pool overlap."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def load_rows(self) -> list[SourceRow]:
        """Read eligible rows read-only; short-description feeds are still wanted."""
        with sqlite3.connect(f"file:{self.db_path.resolve()}?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            records = connection.execute(
                """
                SELECT id, title, description, url, source, category
                FROM source_data
                WHERE source NOT IN ('__EXCLUDED_PLACEHOLDER__')
                  AND (
                    (description IS NOT NULL AND length(description) >= 30)
                    OR source IN (?, ?, ?, ?)
                  )
                ORDER BY fetched_at DESC, id ASC
                """,
                SHORT_DESCRIPTION_SOURCES,
            ).fetchall()
        return [
            SourceRow(
                id=str(row["id"]),
                title=str(row["title"]),
                description=str(row["description"]),
                url=str(row["url"]),
                source=str(row["source"]),
                category=str(row["category"]),
            )
            for row in records
        ]

    def collect(self, count: int, balanced_per_source: int = 1) -> list[list[SourceRow]]:
        """Build ``count`` pools of ten, round-robin across sources."""
        rows = self.load_rows()
        return build_pools(rows, count, balanced_per_source=balanced_per_source)

    def serialize_pool(self, sample_id: str, rows: list[SourceRow]) -> list[dict[str, str]]:
        """Project rows into the curation fixture contract with redacted URLs."""
        return [
            {
                "id": f"{sample_id}-a{index}",
                "title": row["title"],
                "description": row["description"],
                "url": _safe_url(sample_id, index, row["url"]),
                "source": row["source"],
            }
            for index, row in enumerate(rows, start=1)
        ]


def build_pools(
    rows: list[SourceRow], count: int, balanced_per_source: int = 1
) -> list[list[SourceRow]]:
    """Group rows into ``count`` pools of ten with per-source caps (P64.2 default 1)."""
    if count < 1:
        raise ValueError("count must be positive")
    if len(rows) < 10:
        raise ValueError("source_data does not contain ten eligible candidates")
    by_source: dict[str, list[SourceRow]] = {}
    for row in rows:
        by_source.setdefault(row["source"], []).append(row)
    source_order = sorted(s for s in by_source if s not in EXCLUDED_SOURCES)
    cap_per_source = max(balanced_per_source, 1)
    cursors: dict[str, int] = dict.fromkeys(source_order, 0)
    pools: list[list[SourceRow]] = []
    for index in range(count):
        selected: list[SourceRow] = []
        per_source_count: dict[str, int] = dict.fromkeys(source_order, 0)
        seen: set[str] = set()
        rotation = index % len(source_order)
        rotated = source_order[rotation:] + source_order[:rotation]
        for source in rotated:
            if len(selected) >= 10:
                break
            if per_source_count[source] >= cap_per_source:
                continue
            queue = by_source[source]
            cursor = cursors[source]
            if cursor < len(queue) and queue[cursor]["id"] not in seen:
                selected.append(queue[cursor])
                seen.add(queue[cursor]["id"])
                per_source_count[source] += 1
            cursors[source] += 1
        if len(selected) < 10:
            for row in rows:
                if len(selected) >= 10:
                    break
                if row["source"] in EXCLUDED_SOURCES:
                    continue
                if row["id"] not in seen:
                    selected.append(row)
                    seen.add(row["id"])
        if len(selected) < 10:
            raise ValueError("source_data cannot produce a ten-candidate pool")
        pools.append(selected[:10])
    return pools


def _safe_url(sample_id: str, index: int, raw_url: str) -> str:
    """Replace external URLs with stable non-routable fixture URLs."""
    parsed = urlparse(raw_url)
    slug = re.sub(r"[^a-z0-9]+", "-", f"{parsed.netloc}-{parsed.path}".casefold()).strip("-")
    return f"https://example.test/{sample_id}/{index}-{slug[:48] or 'item'}"


__all__ = ["EXCLUDED_SOURCES", "RandomPoolCollector", "SourceRow", "build_pools"]
