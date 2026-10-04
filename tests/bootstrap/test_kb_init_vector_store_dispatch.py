"""Tests for PostgreSQL-only knowledge-base assembly."""

from __future__ import annotations

import pytest

from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings


class _FakeDatabase:
    async def execute(self, statement: str, parameters: tuple[object, ...] = ()) -> int:
        del statement, parameters
        return 0

    async def fetchone(
        self, statement: str, parameters: tuple[object, ...] = ()
    ) -> dict[str, object] | None:
        del statement, parameters
        return None

    async def fetchall(
        self, statement: str, parameters: tuple[object, ...] = ()
    ) -> list[dict[str, object]]:
        del statement, parameters
        return []

    async def close(self) -> None:
        return None

    def set_audit_logger(self, audit_logger: object | None) -> None:
        del audit_logger


@pytest.mark.asyncio
async def test_kb_init_uses_qdrant_store_without_legacy_retriever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P69 always assembles the Qdrant-backed store and no legacy retriever."""
    monkeypatch.setattr("multiscribe_agent.bootstrap.EmbeddingService.is_available", lambda: False)
    context = ServiceContext(SystemSettings(_env_file=None, database_url="postgresql://test"))
    context.db = _FakeDatabase()  # type: ignore[assignment]

    await context._init_kb()

    assert context.kb_service is not None
    assert type(context.kb_service._vector_store).__name__ == "QdrantVectorStore"
    assert not hasattr(context.kb_service, "_retriever")
