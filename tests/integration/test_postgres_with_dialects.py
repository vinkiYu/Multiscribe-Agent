"""Optional PostgreSQL smoke coverage for the dialect-enabled repository path."""

from __future__ import annotations

import os

import pytest

from multiscribe_agent.infra.dialect import PgDialect


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_postgres_dialect_smoke(postgres_container) -> None:
    """The Docker-backed hook is opt-in and always exercises PostgreSQL bind syntax."""
    if os.getenv("INTEGRATION") != "1":
        pytest.skip("set INTEGRATION=1 to run Docker-backed PostgreSQL tests")
    assert postgres_container.get_connection_url()
    assert PgDialect().translate("SELECT ?") == "SELECT $1"
