"""SQLite repository for normalized source content and FTS search."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from multiscribe_agent.domain.models import SourceData, UnifiedData
from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.dialect import DialectRepositoryMixin, PgDialect
from multiscribe_agent.knowledge.fts_query import FtsQueryBuilder

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
    "fetched_at": """
        SELECT * FROM source_data
        WHERE fetched_at BETWEEN ? AND ?
        ORDER BY fetched_at
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


class SourceDataRepository(DialectRepositoryMixin):
    """Persist normalized content, structured filters, and FTS queries."""

    def __init__(self, db: Database) -> None:
        """Create a repository using an initialized database."""
        self._db = db

    async def save_batch(self, items: list[UnifiedData], adapter_name: str) -> int:
        """Upsert the latest source payload and return the number of newly inserted IDs."""
        if not items:
            return 0

        # Read only the IDs in this batch.  A pair of full-table COUNT(*) scans made
        # ingestion progressively slower as the normalized source table grew.
        item_ids = {item.id for item in items}
        existing_ids: set[str] = set()
        # Keep bind lists below SQLite's default variable limit while retaining one
        # query per chunk for unusually large adapter batches.
        item_id_list = list(item_ids)
        for offset in range(0, len(item_id_list), 500):
            chunk = item_id_list[offset : offset + 500]
            placeholders = ", ".join("?" for _ in chunk)
            existing_rows = await self._fetchall(
                f"SELECT id FROM source_data WHERE id IN ({placeholders})",  # noqa: S608
                chunk,
            )
            existing_ids.update(str(row["id"]) for row in existing_rows)

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

        await self._executemany(
            """
            INSERT INTO source_data(
                id, title, url, description, published_date, source, category, author,
                metadata, fetched_at, ingestion_date, adapter_name, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                url = excluded.url,
                description = excluded.description,
                published_date = excluded.published_date,
                source = excluded.source,
                category = excluded.category,
                author = excluded.author,
                metadata = excluded.metadata,
                fetched_at = excluded.fetched_at,
                ingestion_date = excluded.ingestion_date,
                adapter_name = excluded.adapter_name,
                status = excluded.status
            """,
            rows,
        )
        return len(item_ids - existing_ids)

    async def get_recent_candidates(
        self,
        fetch_start: str,
        fetch_end: str,
        published_start: str,
        published_end: str,
    ) -> list[SourceData]:
        """Return rows eligible by either publication or fetch time in one query.

        The digest pipeline applies adapter-specific freshness semantics after this
        broad query.  Keeping the OR in the repository removes a second database
        round-trip while preserving the former publication and snapshot windows.
        """
        rows = await self._fetchall(
            """
            SELECT * FROM source_data
            WHERE (published_date BETWEEN ? AND ?)
               OR (fetched_at BETWEEN ? AND ?)
            ORDER BY published_date, fetched_at
            """,
            [published_start, published_end, fetch_start, fetch_end],
        )
        return [self._to_source_data(row) for row in rows]

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
        rows = await self._fetchall(
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
        rows = await self._fetchall(
            statement,
            parameters,
        )
        return [self._to_source_data(row) for row in rows]

    async def search_fts(
        self, query: str, limit: int, fts_builder: FtsQueryBuilder | None = None
    ) -> list[SourceData]:
        """Search the FTS index and return content with highlighted descriptions."""
        builder = fts_builder or FtsQueryBuilder(
            "postgres" if isinstance(self._dialect, PgDialect) else "sqlite"
        )
        statement, parameters = builder.search_source_data_sql(query, max(limit, 0))
        rows = await self._fetchall(statement, parameters)
        return [self._to_source_data(row, highlight=str(row["highlight"])) for row in rows]

    @staticmethod
    def _pagination_value(value: object, default: int) -> int:
        """Return a non-negative pagination value or its default."""
        if isinstance(value, int) and not isinstance(value, bool):
            return max(value, 0)
        return default

    @staticmethod
    def _to_source_data(row: Mapping[str, Any], highlight: str | None = None) -> SourceData:
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
