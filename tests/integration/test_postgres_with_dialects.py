"""Explicit PostgreSQL-only integration checks."""

from __future__ import annotations

import pytest

from multiscribe_agent.infra.db import init_database
from tests.db import get_test_database_url


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_postgres_schema_exposes_pgvector_and_tsvector() -> None:
    """The production schema uses PostgreSQL vector and full-text primitives."""
    database = await init_database(get_test_database_url())
    try:
        vector = await database.fetchone(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = $1) AS enabled",
            ("vector",),
        )
        table = await database.fetchone(
            "SELECT to_regclass($1) AS name", ("public.source_data_fts",)
        )
        assert vector is not None
        assert vector["enabled"] is True
        assert table is not None
        assert table["name"] == "source_data_fts"
    finally:
        await database.close()
