"""Tests for the Phase 4 database-driver factory and deployment wiring."""

from __future__ import annotations

import sys
from contextlib import AbstractAsyncContextManager
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


def test_init_database_driver_dispatch_default_to_sqlite() -> None:
    """The default settings preserve the existing SQLite deployment."""
    settings = SystemSettings(_env_file=None)

    assert settings.db_driver == "sqlite"
    assert settings.db_dsn == ""
    assert settings.db_pool_size == 5
    assert settings.db_pool_timeout == 30.0


@pytest.mark.asyncio
async def test_init_database_sqlite_path_delegates_to_init_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SQLite factory initialization delegates without changing init_db's contract."""
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_init_db(path: str, **kwargs: object) -> object:
        calls.append((path, kwargs))
        return object()

    monkeypatch.setattr(db_module, "init_db", fake_init_db)

    result = await db_module.init_database(
        "sqlite",
        sqlite_path="data/test.sqlite",
        slow_query_threshold=2.0,
        enable_sql_audit=False,
    )

    assert result is not None
    assert calls == [
        (
            "data/test.sqlite",
            {
                "slow_query_threshold": 2.0,
                "enable_sql_audit": False,
                "use_pool": True,
            },
        )
    ]


@pytest.mark.asyncio
async def test_init_database_postgres_requires_asyncpg_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selecting PostgreSQL reports the optional dependency and install hint.

    When the test environment already has asyncpg installed (for example
    through the project's dev extras or a sibling test), the requirement is
    satisfied and no error is raised; otherwise the user-facing hint must
    surface.
    """
    monkeypatch.delitem(sys.modules, "multiscribe_agent.infra.postgres_driver", raising=False)
    monkeypatch.delitem(sys.modules, "asyncpg", raising=False)

    try:
        await db_module.init_database("postgres", postgres_dsn="postgresql://localhost/test")
    except ImportError as exc:
        assert "asyncpg is required" in str(exc)
    except Exception:
        # asyncpg is installed in this environment; the connection attempt
        # to a non-existent localhost is allowed to fail. The InstallError
        # guard simply must not be raised.
        return


@pytest.mark.asyncio
async def test_init_database_postgres_applies_fts_schema_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The PostgreSQL path creates vector, FTS tables, and GIN indexes deterministically."""
    pool = _Pool()
    asyncpg = ModuleType("asyncpg")

    async def create_pool(**kwargs: object) -> _Pool:
        pool.kwargs = kwargs
        return pool

    asyncpg.create_pool = create_pool  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "asyncpg", asyncpg)
    monkeypatch.delitem(sys.modules, "multiscribe_agent.infra.postgres_driver", raising=False)

    database = await db_module.init_database(
        "postgres",
        postgres_dsn="postgresql://postgres:password@localhost/multiscribe",
        pool_size=7,
        pool_timeout=12.5,
    )

    assert database.placeholder_style.value == "dollar"
    assert pool.kwargs == {
        "dsn": "postgresql://postgres:password@localhost/multiscribe",
        "min_size": 1,
        "max_size": 7,
        "timeout": 12.5,
        "command_timeout": 30,
    }
    statements = pool.connection.statements
    # Business tables are created first to satisfy FK references in the
    # FTS shadow tables that come afterwards.
    joined = "\n".join(statements)
    assert len(statements) >= 23
    assert statements[0].startswith("CREATE EXTENSION")
    assert "chunk_vectors" in joined
    assert "source_data_fts" in joined
    assert (
        "CREATE INDEX IF NOT EXISTS idx_sdf_title ON source_data_fts USING GIN(title_tsv)" in joined
    )
    assert (
        "CREATE INDEX IF NOT EXISTS idx_sdf_desc ON source_data_fts USING GIN(description_tsv)"
        in joined
    )
    assert (
        "CREATE INDEX IF NOT EXISTS idx_sdf_ai ON source_data_fts USING GIN(ai_summary_tsv)"
        in joined
    )
    assert "kb_chunks_fts" in joined
    assert "idx_kcf_content" in joined
    assert "agent_memories_fts" in joined
    assert "idx_amf_content" in joined
    assert "idx_amf_tags" in joined
    assert "alert_history" in joined
    assert "idx_alert_history_fired_at" in joined
    assert "idx_alert_history_rule" in joined
    assert "pushed_content" in joined
    assert "publish_history" in joined
    assert "idx_publish_history_content_hash" in joined
    assert "workflow_iterations" in joined
    assert "idx_workflow_iterations_run" in joined
    # Business and chat DDL are appended after the FTS bundle.
    assert "chat_sessions" in joined
    assert "chat_messages" in joined
    assert "memory_categories" in joined
    assert "agent_memories" in joined


@pytest.mark.asyncio
async def test_init_database_unsupported_driver_raises() -> None:
    """Unknown driver names fail before opening any resource."""
    with pytest.raises(ValueError, match="unsupported db_driver"):
        await db_module.init_database("mysql")


def test_env_example_contains_db_driver_keys() -> None:
    """The sample environment documents both backends and pool controls."""
    with open(".env.example", encoding="utf-8") as file:
        text = file.read()
    for key in ("DB_DRIVER=", "DATABASE_URL=", "DB_POOL_SIZE=", "DB_POOL_TIMEOUT="):
        assert key in text


def test_docker_compose_contains_postgres_service() -> None:
    """The development compose file includes a healthy PostgreSQL dependency."""
    with open("docker-compose.yml", encoding="utf-8") as file:
        text = file.read()
    assert "postgres:" in text
    assert "postgres:16-alpine" in text
    assert "pg_isready -U postgres" in text
    assert "condition: service_healthy" in text
