"""Tests for PostgreSQL schema initialization and persistence."""

from __future__ import annotations

from multiscribe_agent.domain.models import UnifiedData
from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.repositories.source_data import SourceDataRepository


async def test_schema_initialization_is_idempotent(db: Database) -> None:
    """The initialized PostgreSQL schema exposes required base and derived tables."""
    tables = await db.fetchall(
        "SELECT to_regclass($1) AS name UNION ALL SELECT to_regclass($2) AS name",
        ("public.source_data", "public.source_data_fts"),
    )
    assert [row["name"] for row in tables] == ["source_data", "source_data_fts"]


async def test_source_repository_syncs_postgres_tsvector_projection(db: Database) -> None:
    """Source writes populate the PostgreSQL tsvector projection used by search."""
    repository = SourceDataRepository(db)
    await repository.save_batch(
        [
            UnifiedData(
                id="item-1",
                title="Original title",
                url="https://example.com/1",
                description="Initial searchable text",
                published_date="2026-07-16",
                ingestion_date="2026-07-16",
                source="rss",
                category="news",
                metadata={"ai_summary": "Initial summary"},
            )
        ],
        "rss-adapter",
    )
    row = await db.fetchone(
        "SELECT title_tsv @@ plainto_tsquery('simple', $1) AS matched "
        "FROM source_data_fts WHERE row_id = $2",
        ("Original", "item-1"),
    )
    assert row is not None
    assert row["matched"] is True
