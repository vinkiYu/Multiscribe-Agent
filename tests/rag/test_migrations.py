"""Tests for the P66.4 RAG owner migration and KB owner compatibility."""

from __future__ import annotations

import json

import pytest

import multiscribe_agent.bootstrap as bootstrap_module
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings
from multiscribe_agent.domain.models import KBDocument
from multiscribe_agent.infra.db import init_db
from multiscribe_agent.knowledge.document_processor import DocumentProcessor
from multiscribe_agent.knowledge.kb_service import KBService
from multiscribe_agent.knowledge.retriever import Retriever
from multiscribe_agent.rag.indexing import RagIndexRegistry
from multiscribe_agent.rag.migrations import migrate_rag_owner
from multiscribe_agent.rag.schema import RagChunksStore


def test_rag_default_user_is_admin(monkeypatch) -> None:
    """Fresh installs align non-API RAG scope with the JWT subject."""
    monkeypatch.delenv("RAG_DEFAULT_USER_ID", raising=False)
    monkeypatch.delenv("MULTISCRIBE_RAG_DEFAULT_USER_ID", raising=False)

    assert SystemSettings(_env_file=None).rag_default_user_id == "admin"


def test_legacy_kb_json_gets_admin_owner_by_default() -> None:
    """Old JSON blobs remain readable without a batch rewrite."""
    document = KBDocument.model_validate(
        {
            "id": "doc-1",
            "category_id": "cat-1",
            "name": "Legacy",
            "file_name": "legacy.txt",
            "type": "text",
            "summary": "",
            "chunk_count": 0,
            "created_at": 1,
            "updated_at": 1,
        }
    )

    assert document.owner_user_id == "admin"
    assert "owner_user_id" not in json.dumps(document.model_dump(exclude_defaults=True))


@pytest.mark.asyncio
async def test_backfill_rag_owner_is_idempotent(tmp_path) -> None:
    """Only legacy default rows change, and the second run is a no-op."""
    db = await init_db(str(tmp_path / "rag.sqlite"))
    try:
        registry = RagIndexRegistry(db)
        chunks = RagChunksStore(db)
        await registry.ensure_schema()
        await chunks.ensure_schema()
        await db.execute(
            """
            INSERT INTO rag_index_registry(
                chunk_id, document_id, doc_type, content_hash, user_id, indexed_at, index_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("c-1", "d-1", "kb", "hash", "default", "now", "test"),
        )
        await db.execute(
            """
            INSERT INTO rag_chunks(
                chunk_id, document_id, doc_type, user_id, content, content_tsv
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("c-1", "d-1", "kb", "default", "content", "content"),
        )

        first = await migrate_rag_owner(db)
        second = await migrate_rag_owner(db)

        assert first.registry_updated == 1
        assert first.chunks_updated == 1
        assert first.already_marked is False
        assert second.registry_updated == 0
        assert second.chunks_updated == 0
        assert second.already_marked is True
        assert await db.fetchone(
            "SELECT COUNT(*) AS count FROM rag_index_registry WHERE user_id = ?", ("default",)
        ) == {"count": 0}
        assert await db.fetchone(
            "SELECT COUNT(*) AS count FROM rag_chunks WHERE user_id = ?", ("default",)
        ) == {"count": 0}
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_bootstrap_owner_migration_is_fail_open(tmp_path, monkeypatch) -> None:
    """A backend-specific migration exception cannot prevent service startup."""
    db = await init_db(str(tmp_path / "bootstrap.sqlite"))
    context = ServiceContext(SystemSettings(_env_file=None))
    context.db = db

    async def fail_migration(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise LookupError("driver-specific failure")

    monkeypatch.setattr(bootstrap_module, "migrate_rag_owner", fail_migration)
    try:
        await context._migrate_rag_owner()
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_bootstrap_falls_back_when_rag_schema_init_fails(tmp_path, monkeypatch) -> None:
    """The legacy KB service remains usable when RAG setup cannot start."""
    db = await init_db(str(tmp_path / "rag-init.sqlite"))
    context = ServiceContext(SystemSettings(_env_file=None))
    context.db = db

    async def fail_schema(_store: RagChunksStore) -> None:
        raise LookupError("rag schema unavailable")

    monkeypatch.setattr(RagChunksStore, "ensure_schema", fail_schema)
    try:
        await context._init_kb()
        assert context.kb_service is not None
        assert context.rag_service is None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_kb_ingest_persists_owner_user_id(tmp_path) -> None:
    """New KB ingestion writes the owner used by the RAG adapter later."""
    db = await init_db(str(tmp_path / "kb.sqlite"))
    try:
        service = KBService(db, DocumentProcessor(), None, None, Retriever(db, None, None))
        category = await service.create_category("engineering")
        document = await service.ingest_text(
            text="Agent ownership metadata",
            category_id=category.id,
            name="Owner test",
            owner_user_id="member-1",
        )

        assert document.owner_user_id == "member-1"
        loaded = await service.list_documents(category.id)
        assert loaded[0].owner_user_id == "member-1"
    finally:
        await db.close()
