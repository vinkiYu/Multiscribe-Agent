"""Tests for the pgvector adapter without a live PostgreSQL server."""

from __future__ import annotations

import json

import pytest

from multiscribe_agent.infra.postgres.schema_fts import (
    AGENT_MEMORIES_FTS_TABLE,
    CHUNK_VECTORS_TABLE,
    PGVECTOR_EXTENSION,
)
from multiscribe_agent.knowledge.postgres_vector_store import PostgresVectorStore


class _FakeDatabase:
    """Capture parameterized statements used by the Postgres vector adapter."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.rows: list[dict[str, object]] = [{"chunk_id": "c1", "distance": 0.1}]

    async def execute(self, statement: str, parameters: tuple[object, ...] = ()) -> int:
        self.executed.append((statement, parameters))
        return 1

    async def fetchall(
        self, statement: str, parameters: tuple[object, ...] = ()
    ) -> list[dict[str, object]]:
        self.executed.append((statement, parameters))
        return self.rows


@pytest.mark.asyncio
async def test_postgres_vector_store_upsert_and_top_k() -> None:
    """Upsert uses JSON vectors and top-k uses pgvector cosine distance."""
    database = _FakeDatabase()
    store = PostgresVectorStore(database, dim=2)

    await store.upsert("c1", [0.1, 0.2])
    results = await store.top_k([0.1, 0.2], k=3)

    upsert_sql, upsert_params = database.executed[0]
    search_sql, search_params = database.executed[1]
    assert "ON CONFLICT (chunk_id) DO UPDATE" in upsert_sql
    assert json.loads(str(upsert_params[1])) == [0.1, 0.2]
    assert "<=>" in search_sql
    assert "LIMIT $3" in search_sql
    assert json.loads(str(search_params[0])) == [0.1, 0.2]
    assert results == [("c1", 0.1)]


def test_postgres_vector_store_json_format() -> None:
    """The schema and adapter use pgvector's JSON-compatible vector input."""
    assert "vector(384)" in CHUNK_VECTORS_TABLE
    assert PGVECTOR_EXTENSION == "CREATE EXTENSION IF NOT EXISTS vector"
    assert "REFERENCES agent_memories(id)" in AGENT_MEMORIES_FTS_TABLE


@pytest.mark.asyncio
async def test_postgres_vector_store_rejects_wrong_dimensions() -> None:
    """Embedding shape errors fail before any database call."""
    database = _FakeDatabase()
    store = PostgresVectorStore(database, dim=2)

    with pytest.raises(ValueError, match="2 dimensions"):
        await store.upsert("c1", [0.1])
    with pytest.raises(ValueError, match="2 dimensions"):
        await store.top_k([0.1], k=1)
    assert database.executed == []
