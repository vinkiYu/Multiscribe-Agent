"""Tests for backend-specific FTS SQL injection points."""

from __future__ import annotations

from typing import Any

import pytest

from multiscribe_agent.domain.ports import VectorStorePort
from multiscribe_agent.infra.repositories.source_data import SourceDataRepository
from multiscribe_agent.knowledge.fts_query import FtsQueryBuilder
from multiscribe_agent.knowledge.retriever import Retriever
from multiscribe_agent.memory.repositories.memory_entries import MemoryEntryRepository


class _CaptureDatabase:
    """Minimal database double for repository query-builder tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchall(
        self, statement: str, parameters: tuple[object, ...] = ()
    ) -> list[dict[str, Any]]:
        self.calls.append((statement, parameters))
        return []


def test_vector_store_protocol_exists() -> None:
    """The domain port exposes the three required vector operations."""
    assert all(hasattr(VectorStorePort, method) for method in ("upsert", "delete", "top_k"))


def test_fts_query_builder_backend_property() -> None:
    """SQLite and PostgreSQL are explicit builder backends."""
    assert FtsQueryBuilder("sqlite").backend == "sqlite"
    assert FtsQueryBuilder("postgres").backend == "postgres"
    with pytest.raises(ValueError, match="unsupported FTS backend"):
        FtsQueryBuilder("mysql")


def test_fts_query_builder_sqlite_fallback() -> None:
    """SQLite retains its rowid-backed FTS5 query shape."""
    statement, parameters = FtsQueryBuilder("sqlite").search_chunks_sql("python", 10)

    assert "JOIN kb_chunks ON kb_chunks.rowid = kb_chunks_fts.rowid" in statement
    assert "MATCH ?" in statement
    assert parameters == ("python", 10)


def test_fts_query_builder_postgres_sql() -> None:
    """Postgres uses explicit FTS keys, tsvector, and plainto_tsquery."""
    statement, parameters = FtsQueryBuilder("postgres").search_chunks_sql("大语言模型", 10)

    assert "tsvector" not in statement
    assert "content_tsv" in statement
    assert "plainto_tsquery" in statement
    assert "JOIN kb_chunks kc ON kc.id = kcf.chunk_id" in statement
    assert len(parameters) == 3


@pytest.mark.asyncio
async def test_retriever_accepts_fts_builder() -> None:
    """Retriever accepts an injected backend-specific query builder."""
    database = _CaptureDatabase()
    retriever = Retriever(database, fts_builder=FtsQueryBuilder("postgres"))

    assert retriever._fts_builder.backend == "postgres"


@pytest.mark.asyncio
async def test_retriever_uses_fts_builder() -> None:
    """Retriever delegates FTS SQL construction to the injected builder."""
    database = _CaptureDatabase()
    retriever = Retriever(database, fts_builder=FtsQueryBuilder("postgres"))

    assert await retriever._fts_chunk_ids("python", 5) == []
    assert "plainto_tsquery" in database.calls[0][0]


@pytest.mark.asyncio
async def test_source_data_search_fts_accepts_fts_builder() -> None:
    """Source data search forwards its builder to the database."""
    database = _CaptureDatabase()
    await SourceDataRepository(database).search_fts(
        "python", 5, fts_builder=FtsQueryBuilder("postgres")
    )

    assert "ts_headline" in database.calls[0][0]


@pytest.mark.asyncio
async def test_memory_entries_fts_search_accepts_fts_builder() -> None:
    """Memory search forwards its builder to the database."""
    database = _CaptureDatabase()
    await MemoryEntryRepository(database).fts_search(
        "python", 5, fts_builder=FtsQueryBuilder("postgres")
    )

    assert "agent_memories_fts" in database.calls[0][0]
    assert "plainto_tsquery" in database.calls[0][0]
