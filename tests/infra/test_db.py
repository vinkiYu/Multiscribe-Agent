"""Tests for SQLite schema initialization, FTS triggers, and recovery behavior."""

import json

from multiscribe_agent.infra.db import Database, init_db, init_schema


async def test_schema_initialization_is_idempotent(db: Database) -> None:
    """Reapplying the schema succeeds and leaves required tables available."""
    await init_schema(db)

    row = await db.fetchone(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'source_data'",
    )

    assert row is not None
    assert row["name"] == "source_data"


async def test_source_fts_triggers_sync_insert_update_and_delete(db: Database) -> None:
    """Source FTS rows track writes to the source_data content table."""
    await db.execute(
        """
        INSERT INTO source_data(
            id, title, url, description, published_date, source, category, author,
            metadata, fetched_at, ingestion_date, adapter_name, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "item-1",
            "Original title",
            "https://example.com/1",
            "Initial searchable text",
            "2026-07-16",
            "rss",
            "news",
            None,
            json.dumps({"ai_summary": "Initial summary"}),
            "2026-07-16T00:00:00Z",
            "2026-07-16",
            "rss-adapter",
            None,
        ),
    )
    inserted = await db.fetchone(
        "SELECT COUNT(*) FROM source_data_fts WHERE source_data_fts MATCH ?",
        ("Initial",),
    )

    assert inserted is not None
    assert inserted[0] == 1

    await db.execute(
        "UPDATE source_data SET description = ?, metadata = ? WHERE id = ?",
        ("Updated searchable text", json.dumps({"ai_summary": "Updated summary"}), "item-1"),
    )
    updated = await db.fetchone(
        "SELECT COUNT(*) FROM source_data_fts WHERE source_data_fts MATCH ?",
        ("Updated",),
    )

    assert updated is not None
    assert updated[0] == 1

    await db.execute("DELETE FROM source_data WHERE id = ?", ("item-1",))
    deleted = await db.fetchone(
        "SELECT COUNT(*) FROM source_data_fts WHERE source_data_fts MATCH ?",
        ("Updated",),
    )

    assert deleted is not None
    assert deleted[0] == 0


async def test_init_db_sets_wal_and_repairs_running_tasks(tmp_path) -> None:
    """File databases use WAL, repair tasks, and backfill a missing FTS index."""
    path = tmp_path / "multiscribe.sqlite"
    first = await init_db(str(path))
    try:
        pragma = await first.fetchone("PRAGMA journal_mode")
        assert pragma is not None
        assert str(pragma[0]).lower() == "wal"

        await first.execute(
            """
            INSERT INTO task_logs(task_id, task_name, start_time, status)
            VALUES (?, ?, ?, ?)
            """,
            ("task-1", "Daily ingest", "2026-07-16T00:00:00Z", "running"),
        )
        await first.execute(
            """
            INSERT INTO source_data(
                id, title, url, description, published_date, source, category, author,
                metadata, fetched_at, ingestion_date, adapter_name, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "item-1",
                "Backfill title",
                "https://example.com/backfill",
                "Backfill content",
                "2026-07-16",
                "rss",
                "news",
                None,
                "{}",
                "2026-07-16T00:00:00Z",
                "2026-07-16",
                "rss-adapter",
                None,
            ),
        )
        await first.execute("DELETE FROM source_data_fts")
    finally:
        await first.close()

    second = await init_db(str(path))
    try:
        repaired = await second.fetchone(
            "SELECT status FROM task_logs WHERE task_id = ?",
            ("task-1",),
        )
        assert repaired is not None
        assert repaired["status"] == "interrupted"
        backfilled = await second.fetchone("SELECT COUNT(*) FROM source_data_fts")
        assert backfilled is not None
        assert backfilled[0] == 1
    finally:
        await second.close()


async def test_placeholder_fts_triggers_sync_memory_and_knowledge_rows(db: Database) -> None:
    """Placeholder memory and knowledge FTS tables follow their source rows."""
    await db.execute(
        "INSERT INTO agent_memories(id, content, tags) VALUES (?, ?, ?)",
        ("memory-1", "Remember this article", "news"),
    )
    await db.execute(
        "INSERT INTO kb_chunks(id, document_id, content) VALUES (?, ?, ?)",
        ("chunk-1", "document-1", "Knowledge base content"),
    )

    memory = await db.fetchone(
        "SELECT COUNT(*) FROM agent_memories_fts WHERE agent_memories_fts MATCH ?",
        ("Remember",),
    )
    knowledge = await db.fetchone(
        "SELECT COUNT(*) FROM kb_chunks_fts WHERE kb_chunks_fts MATCH ?",
        ("Knowledge",),
    )

    assert memory is not None
    assert knowledge is not None
    assert memory[0] == 1
    assert knowledge[0] == 1
