"""Sample unannotated candidate pools from the persisted source_data table.

The output is deliberately unlabelled.  A product owner must review each pool
and add ``expected_selected_ids``, ``expected_rejected_ids`` and
``selection_rationale`` before it becomes a regression dataset.
"""

from __future__ import annotations

import argparse
import json
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


def main() -> None:
    """Sample deterministic candidate pools and write JSON fixtures."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/database.sqlite", help="SQLite source database")
    parser.add_argument("--count", type=int, default=15, help="Number of pools to write")
    parser.add_argument(
        "--output",
        default="tests/eval/fixtures",
        help="Output directory or a .json path for one pool",
    )
    parser.add_argument("--start-index", type=int, default=6, help="First cr-NNN fixture index")
    args = parser.parse_args()
    if args.count < 1 or args.start_index < 1:
        parser.error("--count and --start-index must be positive")

    rows = _load_rows(Path(args.db))
    pools = _build_pools(rows, args.count)
    output = Path(args.output)
    if output.suffix.casefold() == ".json" and args.count != 1:
        parser.error("a .json output path can only be used with --count 1")
    if output.suffix.casefold() != ".json":
        output.mkdir(parents=True, exist_ok=True)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
    for offset, candidates in enumerate(pools):
        sample_id = f"cr-{args.start_index + offset:03d}"
        fixture = {"candidates": _serialize_candidates(sample_id, candidates)}
        target = (
            output
            if output.suffix.casefold() == ".json"
            else output / f"cr_{args.start_index + offset:03d}.json"
        )
        target.write_text(
            json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(target)


def _load_rows(db_path: Path) -> list[SourceRow]:
    """Read eligible rows without mutating the runtime database."""
    with sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        records = connection.execute(
            """
            SELECT id, title, description, url, source, category
            FROM source_data
            WHERE description IS NOT NULL AND length(description) >= 30
              AND source NOT IN ('__EXCLUDED_PLACEHOLDER__')
            ORDER BY fetched_at DESC, id ASC
            """
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


def _build_pools(rows: list[SourceRow], count: int) -> list[list[SourceRow]]:
    """Build ``count`` pools of 10 with minimal candidate overlap across pools.

    Rows are grouped by source. Each pool pulls one row from up to 10 different
    sources (round-robin), advancing the per-source cursor so consecutive pools
    consume different rows. This ensures 50 pools draw from close to 500 unique
    rows rather than re-reading the same handful.
    """
    if len(rows) < 10:
        raise ValueError("source_data does not contain ten eligible candidates")
    by_source: dict[str, list[SourceRow]] = {}
    for row in rows:
        by_source.setdefault(row["source"], []).append(row)
    # 完全排除的源(非 AI 资讯):
    # - GitHub Blog: 营销/财务/教程为主
    # - AWS 两个源(Artificial Intelligence + AI): 主要是 Bedrock 教程/AWS 营销案例
    EXCLUDED_SOURCES = {"The GitHub Blog", "Artificial Intelligence", "AI"}
    # 按数据量从大到小排
    source_order = sorted(
        [s for s in by_source if s not in EXCLUDED_SOURCES],
        key=lambda s: -len(by_source[s]),
    )
    cursors: dict[str, int] = dict.fromkeys(source_order, 0)
    pools: list[list[SourceRow]] = []
    for index in range(count):
        selected: list[SourceRow] = []
        seen: set[str] = set()
        # Rotate the starting source so no single source always fills slot 1.
        rotation = index % len(source_order)
        rotated = source_order[rotation:] + source_order[:rotation]
        for source in rotated:
            if len(selected) >= 10:
                break
            queue = by_source[source]
            cursor = cursors[source]
            if cursor < len(queue) and queue[cursor]["id"] not in seen:
                selected.append(queue[cursor])
                seen.add(queue[cursor]["id"])
            cursors[source] += 1
        # If round-robin did not fill 10 (some sources exhausted), top up from
        # any remaining unused rows.
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


def _title_key(title: str) -> str:
    """Normalize titles enough to discover cross-source duplicate candidates."""
    return re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()


_GROUP_ORDER = (
    "duplicate",
    "non_ai",
    "non_ai_open_source",
    "academic",
    "marketing",
    "funding",
    "general",
)


def _group_sequence(index: int) -> tuple[str, ...]:
    """Rotate boundary groups so adjacent fixtures do not share one shape."""
    rotation = index % len(_GROUP_ORDER)
    rotated = _GROUP_ORDER[rotation:] + _GROUP_ORDER[:rotation]
    return (*rotated, "general")


def _classify(row: SourceRow) -> str:
    """Classify obvious boundary cases; semantic labels remain human-owned."""
    text = f"{row['title']} {row['description']} {row['source']} {row['category']}".casefold()
    source = row["source"].casefold()
    if re.search(r"funding|raises|raised|融资|估值", text):
        return "funding"
    if "arxiv" in source or "arxiv" in text or "paper" in text or "论文" in text:
        return "academic"
    if any(token in text for token in ("see how", "customer story", "case study", "enterprise")):
        return "marketing"
    if ("github" in source or "github" in row["url"].casefold()) and not any(
        token in text for token in (" ai ", "llm", "agent", "rag", "model")
    ):
        return "non_ai_open_source"
    if not any(token in text for token in ("ai", "llm", "agent", "rag", "machine learning")):
        return "non_ai"
    return "general"


def _serialize_candidates(sample_id: str, rows: list[SourceRow]) -> list[dict[str, str]]:
    """Project rows into the curation fixture contract and redact real URLs."""
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


def _safe_url(sample_id: str, index: int, raw_url: str) -> str:
    """Replace external URLs with stable non-routable fixture URLs."""
    parsed = urlparse(raw_url)
    slug = re.sub(r"[^a-z0-9]+", "-", f"{parsed.netloc}-{parsed.path}".casefold()).strip("-")
    return f"https://example.test/{sample_id}/{index}-{slug[:48] or 'item'}"


if __name__ == "__main__":
    main()
