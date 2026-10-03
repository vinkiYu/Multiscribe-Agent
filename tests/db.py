"""PostgreSQL test-database helpers shared by the migrated test suite."""

from __future__ import annotations

import atexit
import os
from typing import Any

from multiscribe_agent.infra.db import Database, init_database

_TRUNCATE_SQL = """
DO $$
DECLARE
    _table text;
BEGIN
    FOR _table IN
        SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    LOOP
        EXECUTE 'TRUNCATE TABLE public.' || quote_ident(_table) || ' RESTART IDENTITY CASCADE';
    END LOOP;
END $$
"""

_container_manager: Any | None = None
_container_dsn: str | None = None


def _normalize_asyncpg_dsn(dsn: str) -> str:
    """Convert SQLAlchemy-style PostgreSQL URLs to an asyncpg DSN."""
    for scheme in ("postgresql+psycopg2://", "postgresql+psycopg://"):
        if dsn.startswith(scheme):
            return "postgresql://" + dsn.removeprefix(scheme)
    return dsn


def get_test_database_url() -> str:
    """Return TEST_DATABASE_URL or lazily start the mandated PG container."""
    configured = os.getenv("TEST_DATABASE_URL", "").strip()
    if configured:
        return _normalize_asyncpg_dsn(configured)

    global _container_manager, _container_dsn
    if _container_dsn:
        return _container_dsn
    try:
        from testcontainers.community.postgres import PostgresContainer
    except ImportError as exc:  # pragma: no cover - dependency is required by test extra.
        raise RuntimeError("test extra must include testcontainers") from exc

    manager = PostgresContainer("pgvector/pgvector:pg16")
    try:
        container = manager.__enter__()
    except Exception as exc:  # pragma: no cover - depends on local Docker daemon.
        raise RuntimeError(
            "PostgreSQL tests require Docker or TEST_DATABASE_URL; container startup failed"
        ) from exc
    _container_manager = manager
    _container_dsn = _normalize_asyncpg_dsn(container.get_connection_url())
    atexit.register(_stop_container)
    return _container_dsn


def _stop_container() -> None:
    """Stop the lazy testcontainer when the test process exits."""
    if _container_manager is not None:
        _container_manager.__exit__(None, None, None)


async def init_test_database() -> Database:
    """Create a clean PostgreSQL database handle for one test."""
    database = await init_database(get_test_database_url(), enable_sql_audit=False)
    await truncate_all_tables(database)
    return database


async def truncate_all_tables(database: Database) -> None:
    """Truncate every public table so one test cannot observe another's rows."""
    await database.execute(_TRUNCATE_SQL)
