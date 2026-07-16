"""SQLite repository for normalized source content and FTS search."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

import aiosqlite

from multiscribe_agent.domain.models import SourceData, UnifiedData
from multiscribe_agent.infra.db import Database

_DATE_RANGE_STATEMENTS = {
    "ingestion_date": """
        SELECT * FROM source_data
        WHERE ingestion_date BETWEEN ? AND ?
        ORDER BY ingestion_date
    """,
    "published_date": """
        SELECT * FROM source_data
        WHERE published_date BETWEEN ? AND ?
        ORDER BY published_date
    """,
}

_FILTER_STATEMENTS = {
    (False, False, False): """
        SELECT * FROM source_data
        ORDER BY fetched_at DESC
        LIMIT ? OFFSET ?
    """,
    (True, False, False): """
        SELECT * FROM source_data
        WHERE source = ?
        ORDER BY fetched_at DESC
        LIMIT ? OFFSET ?
    """,
    (False, True, False): """
        SELECT * FROM source_data
        WHERE category = ?
        ORDER BY fetched_at DESC
        LIMIT ? OFFSET ?
    """,
    (False, False, True): """
        SELECT * FROM source_data
        WHERE status = ?
        ORDER BY fetched_at DESC
        LIMIT ? OFFSET ?
    """,
    (True, True, False): """
        SELECT * FROM source_data
        WHERE source = ? AND category = ?
        ORDER BY fetched_at DESC
        LIMIT ? OFFSET ?
    """,
    (True, False, True): """
        SELECT * FROM source_data
        WHERE source = ? AND status = ?
        ORDER BY fetched_at DESC
        LIMIT ? OFFSET ?
    """,
    (False, True, True): """
        SELECT * FROM source_data
        WHERE category = ? AND status = ?
        ORDER BY fetched_at DESC
        LIMIT ? OFFSET ?
    """,
    (True, True, True): """
        SELECT * FROM source_data
        WHERE source = ? AND category = ? AND status = ?
        ORDER BY fetched_at DESC
        LIMIT ? OFFSET ?
    """,
}


class SourceDataRepository:
    """Persist normalized content, structured filters, and FTS queries."""

    def __init__(self, db: Database) -> None:
        """Create a repository using an initialized database."""
        self._db = db

    async def save_batch(self, items: list[UnifiedData], adapter_name: str) -> int:
        """Insert new items by ID and return the number of rows actually inserted."""
        if not items:
            return 0

        count_before = await self._db.fetchone("SELECT COUNT(*) FROM source_data")
        if count_before is None:
            raise RuntimeError("source_data table is unavailable")

        fetched_at = datetime.now(UTC).isoformat()
        rows: list[tuple[object, ...]] = []
        for item in items:
            rows.append(
                (
                    item.id,
                    item.title,
                    item.url,
                    item.description,
                    item.published_date,
                    item.source,
                    item.category,
                    item.author,
                    json.dumps(item.metadata),
                    fetched_at,
                    item.ingestion_date or fetched_at,
                    adapter_name,
                    item.status,
                )
            )

        await self._db.executemany(
            """
            INSERT OR IGNORE INTO source_data(
                id, title, url, description, published_date, source, category, author,
                metadata, fetched_at, ingestion_date, adapter_name, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        count_after = await self._db.fetchone("SELECT COUNT(*) FROM source_data")
        if count_after is None:
            raise RuntimeError("source_data table is unavailable")
        return int(count_after[0]) - int(count_before[0])

    async def get_by_date_range(
        self,
        start: str,
        end: str,
        query_field: str = "ingestion_date",
    ) -> list[SourceData]:
        """Return content whose selected date field is within an inclusive range."""
        statement = _DATE_RANGE_STATEMENTS.get(query_field)
        if statement is None:
            raise ValueError(f"unsupported date field: {query_field}")
        rows = await self._db.fetchall(
            statement,
            (start, end),
        )
        return [self._to_source_data(row) for row in rows]

    async def query(self, filters: dict[str, Any]) -> list[SourceData]:
        """Filter content by source, category, status, limit, and offset."""
        parameters: list[object] = []
        filter_values: list[str | None] = []
        for field in ("source", "category", "status"):
            value = filters.get(field)
            if isinstance(value, str):
                parameters.append(value)
                filter_values.append(value)
            else:
                filter_values.append(None)

        limit = self._pagination_value(filters.get("limit"), default=100)
        offset = self._pagination_value(filters.get("offset"), default=0)
        filter_key: tuple[bool, bool, bool] = (
            filter_values[0] is not None,
            filter_values[1] is not None,
            filter_values[2] is not None,
        )
        statement = _FILTER_STATEMENTS[filter_key]
        parameters.extend((limit, offset))
        rows = await self._db.fetchall(
            statement,
            parameters,
        )
        return [self._to_source_data(row) for row in rows]

    async def search_fts(self, query: str, limit: int) -> list[SourceData]:
        """Search the FTS index and return content with highlighted descriptions."""
        rows = await self._db.fetchall(
            """
            SELECT source_data.*,
                snippet(source_data_fts, 1, '<mark>', '</mark>', '...', 12) AS highlight
            FROM source_data_fts
            JOIN source_data ON source_data_fts.rowid = source_data.rowid
            WHERE source_data_fts MATCH ?
            ORDER BY bm25(source_data_fts)
            LIMIT ?
            """,
            (query, max(limit, 0)),
        )
        return [self._to_source_data(row, highlight=str(row["highlight"])) for row in rows]

    @staticmethod
    def _pagination_value(value: object, default: int) -> int:
        """Return a non-negative pagination value or its default."""
        if isinstance(value, int) and not isinstance(value, bool):
            return max(value, 0)
        return default

    @staticmethod
    def _to_source_data(row: aiosqlite.Row, highlight: str | None = None) -> SourceData:
        """Convert a SQLite row into a validated SourceData model."""
        data = dict(row)
        data["metadata"] = SourceDataRepository._decode_metadata(str(data["metadata"]))
        if highlight is not None:
            data["description"] = highlight
        return SourceData.model_validate(data)

    @staticmethod
    def _decode_metadata(raw_value: str) -> dict[str, Any]:
        """Decode a metadata JSON object stored by this repository."""
        value = json.loads(raw_value)
        if not isinstance(value, dict):
            raise ValueError("source metadata must be a JSON object")
        return cast(dict[str, Any], value)
