"""Explicit PostgreSQL smoke coverage for the PG-only backend."""

from __future__ import annotations

import pytest

from multiscribe_agent.infra.db import init_database
from tests.db import get_test_database_url


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_postgres_bootstrap_smoke() -> None:
    """A configured PostgreSQL instance accepts the initialized schema."""
    database = await init_database(get_test_database_url())
    try:
        row = await database.fetchone("SELECT 1 AS value")
        assert row is not None
        assert row["value"] == 1
    finally:
        await database.close()
