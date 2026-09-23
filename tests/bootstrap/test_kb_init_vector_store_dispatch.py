"""Tests for backend-aware knowledge-base assembly in ServiceContext."""

from __future__ import annotations

import pytest

from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings
from multiscribe_agent.infra.db_protocol import PlaceholderStyle


class _FakeDatabase:
    def __init__(self, style: PlaceholderStyle) -> None:
        self.placeholder_style = style
        self.migrate_calls = 0

    async def migrate_kb(self) -> bool:
        self.migrate_calls += 1
        return True


@pytest.mark.asyncio
async def test_kb_init_does_not_construct_legacy_retriever(monkeypatch: pytest.MonkeyPatch) -> None:
    """P66.6 removes the legacy Retriever from KB service assembly."""
    monkeypatch.setattr("multiscribe_agent.bootstrap.EmbeddingService.is_available", lambda: False)

    for style in (PlaceholderStyle.QUESTION_MARK, PlaceholderStyle.DOLLAR):
        context = ServiceContext(SystemSettings(_env_file=None))
        database = _FakeDatabase(style)
        context.db = database  # type: ignore[assignment]

        await context._init_kb()

        assert context.kb_service is not None
        assert not hasattr(context.kb_service, "_retriever")


@pytest.mark.asyncio
async def test_kb_init_sqlite_uses_vector_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """SQLite keeps the existing sqlite-vec adapter and migration call."""
    monkeypatch.setattr("multiscribe_agent.bootstrap.EmbeddingService.is_available", lambda: False)
    context = ServiceContext(SystemSettings(_env_file=None))
    database = _FakeDatabase(PlaceholderStyle.QUESTION_MARK)
    context.db = database  # type: ignore[assignment]

    await context._init_kb()

    assert context.kb_service is not None
    assert type(context.kb_service._vector_store).__name__ == "VectorStore"
    assert database.migrate_calls == 1


@pytest.mark.asyncio
async def test_kb_init_postgres_uses_postgres_vector_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PostgreSQL uses pgvector and trusts the factory-applied schema."""
    monkeypatch.setattr("multiscribe_agent.bootstrap.EmbeddingService.is_available", lambda: False)
    context = ServiceContext(SystemSettings(_env_file=None))
    database = _FakeDatabase(PlaceholderStyle.DOLLAR)
    context.db = database  # type: ignore[assignment]

    await context._init_kb()

    assert context.kb_service is not None
    assert type(context.kb_service._vector_store).__name__ == "PostgresVectorStore"
    assert database.migrate_calls == 0
