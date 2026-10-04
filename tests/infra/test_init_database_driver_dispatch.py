"""Tests for the PostgreSQL-only database factory."""

from __future__ import annotations

import sys
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from multiscribe_agent.config import SystemSettings
from multiscribe_agent.infra import db as db_module


class _Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement: str) -> str:
        self.statements.append(statement)
        return "CREATE 0"


class _Acquire(AbstractAsyncContextManager[_Connection]):
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        return None


class _Pool:
    def __init__(self) -> None:
        self.connection = _Connection()
        self.kwargs: dict[str, object] = {}

    def acquire(self) -> _Acquire:
        return _Acquire(self.connection)

    async def close(self) -> None:
        return None


def test_settings_expose_database_url_without_driver_switch() -> None:
    settings = SystemSettings(_env_file=None, database_url="postgresql://localhost/test")
    assert settings.database_url.endswith("/test")
    assert settings.db_pool_size == 5
    assert settings.db_pool_timeout == 30.0


@pytest.mark.asyncio
async def test_init_database_rejects_blank_dsn() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        await db_module.init_database("")


@pytest.mark.asyncio
async def test_init_database_applies_postgres_schema_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _Pool()
    asyncpg = ModuleType("asyncpg")

    async def create_pool(**kwargs: object) -> _Pool:
        pool.kwargs = kwargs
        return pool

    asyncpg.create_pool = create_pool  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "asyncpg", asyncpg)

    database = await db_module.init_database(
        "postgresql://postgres:password@localhost/multiscribe",
        pool_size=7,
        pool_timeout=12.5,
    )
    assert pool.kwargs == {
        "dsn": "postgresql://postgres:password@localhost/multiscribe",
        "min_size": 1,
        "max_size": 7,
        "timeout": 12.5,
        "command_timeout": 30,
    }
    statements = pool.connection.statements
    joined = "\n".join(statements)
    assert "source_data_fts" in joined
    assert "kb_chunks_fts" in joined
    assert "agent_memories_fts" in joined
    assert "alert_history" in joined
    assert "pushed_content" in joined
    assert "publish_history" in joined
    assert "workflow_iterations" in joined
    assert "chat_sessions" in joined
    await database.close()


def test_env_example_documents_database_url() -> None:
    text = Path(".env.example").read_text(encoding="utf-8")
    assert "DATABASE_URL=" in text
    assert "DB_POOL_SIZE=" in text
    assert "DB_POOL_TIMEOUT=" in text


def test_docker_compose_contains_postgres_service() -> None:
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "postgres:" in text
    assert "pg_isready" in text
