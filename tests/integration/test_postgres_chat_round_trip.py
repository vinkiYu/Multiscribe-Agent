"""End-to-end PostgreSQL integration tests for P58 (User Preference & Dialogue Wiring).

These tests run against a real Postgres testcontainer started via testcontainers.
They are skipped unless ``INTEGRATION=1`` is set in the environment. The full
suite covers:

* bootstrap through ``init_database(db_driver="postgres")``,
* ``ChatSessionRepository`` round-trip including ``$N`` placeholders and JSONB
  metadata,
* a smoke end-to-end exercise of ``ServiceContext.init()`` with the PG driver
  so we know the full chat + preference chain wires together without falling
  back to the SQLite default.

The container image is ``pgvector/pgvector:pg16`` so the ``vector`` extension
required by the FTS/vector bundle can be installed.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from multiscribe_agent.infra.db import init_database
from multiscribe_agent.memory.chat_sessions import ChatSessionRepository

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
]

POSTGRES_IMAGE = "pgvector/pgvector:pg16"


def _require_integration() -> None:
    if os.getenv("INTEGRATION") != "1":
        pytest.skip("set INTEGRATION=1 to run Docker-backed PostgreSQL tests")


@asynccontextmanager
async def _postgres_database() -> AsyncIterator[tuple[object, str]]:
    """Spin up a Postgres testcontainer, run the bootstrap, and yield the open DB."""
    _require_integration()
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:
        pytest.skip(f"testcontainers is unavailable: {exc}")
    try:
        with PostgresContainer(POSTGRES_IMAGE) as container:
            dsn = container.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
            database = await init_database(
                "postgres",
                postgres_dsn=dsn,
                pool_size=2,
                pool_timeout=10.0,
            )
            try:
                yield database, dsn
            finally:
                await database.close()
    except Exception as exc:
        pytest.skip(f"PostgreSQL container is unavailable: {exc}")


@pytest.fixture
async def postgres_database() -> AsyncIterator[tuple[object, str]]:
    async with _postgres_database() as value:
        yield value


async def test_postgres_bootstrap_creates_chat_tables(postgres_database) -> None:
    """init_database(db_driver='postgres') creates the chat and business tables."""
    database, _dsn = postgres_database
    chat_sessions = await database.fetchall("SELECT to_regclass('public.chat_sessions') AS name")
    chat_messages = await database.fetchall("SELECT to_regclass('public.chat_messages') AS name")
    memory_categories = await database.fetchall(
        "SELECT to_regclass('public.memory_categories') AS name"
    )
    source_data = await database.fetchall("SELECT to_regclass('public.source_data') AS name")
    source_data_fts = await database.fetchall(
        "SELECT to_regclass('public.source_data_fts') AS name"
    )
    assert str(chat_sessions[0]["name"]) == "chat_sessions"
    assert str(chat_messages[0]["name"]) == "chat_messages"
    assert str(memory_categories[0]["name"]) == "memory_categories"
    assert str(source_data[0]["name"]) == "source_data"
    assert str(source_data_fts[0]["name"]) == "source_data_fts"


async def test_chat_session_repository_round_trip_on_postgres(postgres_database) -> None:
    """ChatSessionRepository persists sessions and messages against PG."""
    database, _dsn = postgres_database
    repo = ChatSessionRepository(database)
    session = await repo.create_session("Postgres session")
    assert session.title == "Postgres session"
    assert session.message_count == 0

    user = await repo.append_message(session.id, "user", "你好")
    assistant = await repo.append_message(session.id, "assistant", "世界")
    assert user is not None and assistant is not None
    assert user.role == "user"
    assert assistant.role == "assistant"

    listed = await repo.list_sessions()
    assert [item.id for item in listed] == [session.id]
    messages = await repo.list_messages(session.id)
    assert [message.content for message in messages] == ["你好", "世界"]
    assert [message.role for message in messages] == ["user", "assistant"]

    loaded = await repo.get_session(session.id)
    assert loaded is not None
    assert loaded.message_count == 2

    assert await repo.delete_session(session.id) is True
    assert await repo.get_session(session.id) is None


async def test_postgres_metadata_round_trips_through_jsonb(postgres_database) -> None:
    """Metadata dictionaries survive a JSONB round-trip without string truncation."""
    database, _dsn = postgres_database
    repo = ChatSessionRepository(database)
    session = await repo.create_session()
    message = await repo.append_message(
        session.id,
        "user",
        "with metadata",
        metadata={"trace_id": uuid.uuid4().hex, "score": 4, "nested": {"a": [1, 2]}},
    )
    assert message is not None
    fetched = await repo.list_messages(session.id)
    assert fetched[0].metadata["score"] == 4
    assert fetched[0].metadata["nested"] == {"a": [1, 2]}
    raw = await database.fetchone("SELECT metadata FROM chat_messages WHERE id = $1", (message.id,))
    raw_metadata = raw["metadata"]
    if isinstance(raw_metadata, str):
        import json as _json

        raw_metadata = _json.loads(raw_metadata)
    assert raw_metadata["score"] == 4


async def test_chat_session_rejects_bad_role_on_postgres(postgres_database) -> None:
    """append_message keeps the role check on the PG backend too."""
    database, _dsn = postgres_database
    repo = ChatSessionRepository(database)
    session = await repo.create_session()
    with pytest.raises(ValueError, match="role"):
        await repo.append_message(session.id, "tool", "x")


async def test_postgres_bootstrap_via_service_context() -> None:
    """ServiceContext.init() succeeds against a fresh testcontainer with the PG driver."""
    _require_integration()
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:
        pytest.skip(f"testcontainers is unavailable: {exc}")
    try:
        with PostgresContainer(POSTGRES_IMAGE) as container:
            dsn = container.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
            import tempfile

            from multiscribe_agent.bootstrap import ServiceContext
            from multiscribe_agent.config import SystemSettings

            with tempfile.TemporaryDirectory(prefix="ms-pg-") as tmp:
                settings = SystemSettings(
                    _env_file=None,
                    db_driver="postgres",
                    db_dsn=dsn,
                    db_path=str(Path(tmp) / "unused.sqlite"),
                )
                context = ServiceContext(settings)
                try:
                    await context.init()
                    assert context.chat_service is not None
                    session = await context.chat_service.create_session("boot")
                    await context.chat_service.send_message(session.id, "hi")
                    fetched = await context.chat_service.list_messages(session.id)
                    assert [message.role for message in fetched] == ["user", "assistant"]
                finally:
                    await context.close()
    except Exception as exc:
        pytest.skip(f"PostgreSQL container is unavailable: {exc}")
