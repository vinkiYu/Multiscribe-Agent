"""Tests for resumable rebuild command bookkeeping."""

from __future__ import annotations

import pytest

from scripts.rebuild_rag_index import (
    _existing_index_versions,
    _read_cursor,
    _reset_derived_index,
    _write_cursor,
    build_parser,
)
from tests.db import init_test_database


def test_rebuild_defaults_to_incremental_and_cursor_round_trip(tmp_path) -> None:
    """The command resumes from a persisted document_id without changing data."""
    args = build_parser().parse_args([])
    assert args.full is False
    assert args.resume is False

    cursor = tmp_path / "cursor.json"
    _write_cursor(cursor, "kb:document-2")
    assert _read_cursor(cursor) == "kb:document-2"


def test_malformed_cursor_starts_from_beginning(tmp_path) -> None:
    """A partial cursor cannot make a rebuild skip documents silently."""
    cursor = tmp_path / "cursor.json"
    cursor.write_text("not-json", encoding="utf-8")

    assert _read_cursor(cursor) == ""


@pytest.mark.asyncio
async def test_model_change_resets_postgres_derived_index() -> None:
    """A model switch clears stale manifests and PostgreSQL vector rows."""
    db = await init_test_database()
    try:
        await db.execute(
            """INSERT INTO rag_index_registry(
                chunk_id, document_id, doc_type, content_hash, user_id, indexed_at, index_version
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            ("chunk-1", "doc-1", "kb", "hash", "admin", "now", "20260922-old-model"),
        )
        assert await _existing_index_versions(db) == {"20260922-old-model"}

        await _reset_derived_index(db, 512)

        assert await db.fetchall("SELECT * FROM rag_index_registry") == []
        assert await db.fetchall("SELECT * FROM rag_chunks") == []
        assert await db.fetchall("SELECT * FROM chunk_vectors") == []
    finally:
        await db.close()
