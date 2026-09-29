"""PostgreSQL-only database bootstrap for MultiscribeAgent.

P67 removes the former SQLite factory and keeps this module as the stable
import path used by the composition root and repositories.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from importlib import import_module
from typing import cast

from multiscribe_agent.infra.db_protocol import DatabaseProtocol
from multiscribe_agent.infra.postgres.schema_business import ALL_BUSINESS_TABLES
from multiscribe_agent.infra.postgres.schema_chat import ALL_CHAT_SCHEMAS
from multiscribe_agent.infra.postgres.schema_dedup import ALL_SCHEMAS as DEDUP_SCHEMAS
from multiscribe_agent.infra.postgres.schema_fts import (
    AGENT_MEMORIES_FTS_INDEXES,
    AGENT_MEMORIES_FTS_TABLE,
    CHUNK_VECTORS_TABLE,
    KB_CHUNKS_FTS_INDEX,
    KB_CHUNKS_FTS_TABLE,
    PGVECTOR_EXTENSION,
    SOURCE_DATA_FTS_INDEXES,
    SOURCE_DATA_FTS_TABLE,
)
from multiscribe_agent.infra.postgres.schema_rag import (
    RAG_CHUNKS_INDEXES,
    RAG_CHUNKS_TABLE,
    RAG_INDEX_REGISTRY_INDEXES,
    RAG_INDEX_REGISTRY_TABLE,
)
from multiscribe_agent.infra.postgres_driver import PostgresDatabase, _AsyncpgPool

Database = PostgresDatabase


async def init_database(
    postgres_dsn: str,
    *,
    pool_size: int = 5,
    pool_timeout: float = 30.0,
    slow_query_threshold: float = 1.0,
    enable_sql_audit: bool = True,
) -> PostgresDatabase:
    """Create a PostgreSQL pool, initialize all application schemas, and return it."""
    if not postgres_dsn.strip():
        raise ValueError("DATABASE_URL is required for the PostgreSQL backend")
    asyncpg_module = import_module("asyncpg")
    create_pool = cast(
        Callable[..., Awaitable[_AsyncpgPool]], asyncpg_module.__dict__["create_pool"]
    )
    pool = await create_pool(
        dsn=postgres_dsn,
        min_size=1,
        max_size=pool_size,
        timeout=pool_timeout,
        command_timeout=30,
    )
    database = PostgresDatabase(
        pool,
        slow_query_threshold=slow_query_threshold,
        enable_sql_audit=enable_sql_audit,
    )
    try:
        await _initialize_schema(database, pool)
    except BaseException:
        await database.close()
        raise
    return database


async def _initialize_schema(database: PostgresDatabase, pool: _AsyncpgPool) -> None:
    """Install extensions, base tables, derived indexes, and idempotency tables."""
    async with pool.acquire() as connection:
        await connection.execute(PGVECTOR_EXTENSION)
        for statement in ALL_BUSINESS_TABLES:
            await connection.execute(statement)
        await connection.execute(CHUNK_VECTORS_TABLE)
        await connection.execute(SOURCE_DATA_FTS_TABLE)
        for statement in SOURCE_DATA_FTS_INDEXES:
            await connection.execute(statement)
        await connection.execute(KB_CHUNKS_FTS_TABLE)
        await connection.execute(KB_CHUNKS_FTS_INDEX)
        await connection.execute(AGENT_MEMORIES_FTS_TABLE)
        for statement in AGENT_MEMORIES_FTS_INDEXES:
            await connection.execute(statement)
        await connection.execute(RAG_INDEX_REGISTRY_TABLE)
        for statement in RAG_INDEX_REGISTRY_INDEXES:
            await connection.execute(statement)
        await connection.execute(RAG_CHUNKS_TABLE)
        for statement in RAG_CHUNKS_INDEXES:
            await connection.execute(statement)
        for statement in DEDUP_SCHEMAS:
            for fragment in statement.split(";"):
                if fragment.strip():
                    await connection.execute(fragment)
        for statement in ALL_CHAT_SCHEMAS:
            await connection.execute(statement)

    database.set_audit_logger(None)


__all__ = ["Database", "DatabaseProtocol", "PostgresDatabase", "init_database"]
