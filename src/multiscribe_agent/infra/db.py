"""SQLite connection management, schema initialization, and FTS indexes."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import aiosqlite

type SqlParameters = Sequence[object]


class Database:
    """Wrap an aiosqlite connection with small typed query helpers."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        """Create a database wrapper around an open connection."""
        self.connection = connection

    @classmethod
    async def open(cls, path: str) -> Database:
        """Open a database connection and apply SQLite runtime settings."""
        connection = await aiosqlite.connect(path)
        connection.row_factory = aiosqlite.Row
        database = cls(connection)
        await database._configure()
        return database

    async def close(self) -> None:
        """Close the underlying SQLite connection."""
        await self.connection.close()

    async def execute(self, statement: str, parameters: SqlParameters = ()) -> int:
        """Execute one write statement, commit it, and return affected rows."""
        cursor = await self.connection.execute(statement, parameters)
        try:
            await self.connection.commit()
            return cursor.rowcount
        finally:
            await cursor.close()

    async def executemany(
        self,
        statement: str,
        parameter_sets: Iterable[SqlParameters],
    ) -> int:
        """Execute a batch write and return the number of database changes."""
        changes_before = self.connection.total_changes
        cursor = await self.connection.executemany(statement, parameter_sets)
        try:
            await self.connection.commit()
            return self.connection.total_changes - changes_before
        finally:
            await cursor.close()

    async def fetchone(
        self,
        statement: str,
        parameters: SqlParameters = (),
    ) -> aiosqlite.Row | None:
        """Return the first row for a parameterized query."""
        cursor = await self.connection.execute(statement, parameters)
        try:
            return await cursor.fetchone()
        finally:
            await cursor.close()

    async def fetchall(
        self,
        statement: str,
        parameters: SqlParameters = (),
    ) -> list[aiosqlite.Row]:
        """Return all rows for a parameterized query."""
        cursor = await self.connection.execute(statement, parameters)
        try:
            return list(await cursor.fetchall())
        finally:
            await cursor.close()

    async def _configure(self) -> None:
        """Apply connection-level SQLite settings required by the application."""
        for statement in (
            "PRAGMA journal_mode=WAL",
            "PRAGMA busy_timeout=5000",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA foreign_keys=ON",
        ):
            cursor = await self.connection.execute(statement)
            await cursor.close()
        await self.connection.commit()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    expires_at REAL
);

CREATE TABLE IF NOT EXISTS commit_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    platform TEXT NOT NULL,
    file_path TEXT NOT NULL,
    commit_message TEXT NOT NULL,
    commit_time TEXT NOT NULL,
    full_content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_data (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    description TEXT NOT NULL,
    published_date TEXT NOT NULL,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    author TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    fetched_at TEXT NOT NULL,
    ingestion_date TEXT NOT NULL,
    adapter_name TEXT NOT NULL,
    status TEXT
);

CREATE INDEX IF NOT EXISTS idx_source_data_source ON source_data(source);
CREATE INDEX IF NOT EXISTS idx_source_data_fetched_at ON source_data(fetched_at);
CREATE INDEX IF NOT EXISTS idx_source_data_status ON source_data(status);
CREATE INDEX IF NOT EXISTS idx_source_data_ingestion_date ON source_data(ingestion_date);
CREATE INDEX IF NOT EXISTS idx_source_data_published_date ON source_data(published_date);
CREATE INDEX IF NOT EXISTS idx_source_data_published_fetched
    ON source_data(published_date, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_data_ingestion_fetched
    ON source_data(ingestion_date, fetched_at DESC);

CREATE TABLE IF NOT EXISTS task_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    task_name TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    duration INTEGER,
    status TEXT NOT NULL,
    progress REAL,
    message TEXT,
    result_count INTEGER
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mcp_configs (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    prefix TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL,
    verification_token TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(prefix);
CREATE INDEX IF NOT EXISTS idx_api_keys_token ON api_keys(verification_token);

CREATE TABLE IF NOT EXISTS embeddings (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    vec BLOB,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS memory_categories (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS agent_memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS kb_categories (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS kb_documents (
    id TEXT PRIMARY KEY,
    category_id TEXT,
    data TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS kb_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT,
    content TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE VIRTUAL TABLE IF NOT EXISTS source_data_fts USING fts5(
    title,
    description,
    ai_summary
);
CREATE TRIGGER IF NOT EXISTS trg_source_data_ai AFTER INSERT ON source_data BEGIN
    INSERT INTO source_data_fts(rowid, title, description, ai_summary)
    VALUES (
        new.rowid,
        new.title,
        new.description,
        COALESCE(json_extract(new.metadata, '$.ai_summary'), '')
    );
END;
CREATE TRIGGER IF NOT EXISTS trg_source_data_ad AFTER DELETE ON source_data BEGIN
    DELETE FROM source_data_fts WHERE rowid = old.rowid;
END;
CREATE TRIGGER IF NOT EXISTS trg_source_data_au AFTER UPDATE ON source_data BEGIN
    DELETE FROM source_data_fts WHERE rowid = old.rowid;
    INSERT INTO source_data_fts(rowid, title, description, ai_summary)
    VALUES (
        new.rowid,
        new.title,
        new.description,
        COALESCE(json_extract(new.metadata, '$.ai_summary'), '')
    );
END;

CREATE VIRTUAL TABLE IF NOT EXISTS agent_memories_fts USING fts5(
    content,
    tags
);
CREATE TRIGGER IF NOT EXISTS trg_agent_memories_ai AFTER INSERT ON agent_memories BEGIN
    INSERT INTO agent_memories_fts(rowid, content, tags)
    VALUES (new.rowid, new.content, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS trg_agent_memories_ad AFTER DELETE ON agent_memories BEGIN
    DELETE FROM agent_memories_fts WHERE rowid = old.rowid;
END;
CREATE TRIGGER IF NOT EXISTS trg_agent_memories_au AFTER UPDATE ON agent_memories BEGIN
    DELETE FROM agent_memories_fts WHERE rowid = old.rowid;
    INSERT INTO agent_memories_fts(rowid, content, tags)
    VALUES (new.rowid, new.content, new.tags);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts USING fts5(
    content
);
CREATE TRIGGER IF NOT EXISTS trg_kb_chunks_ai AFTER INSERT ON kb_chunks BEGIN
    INSERT INTO kb_chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER IF NOT EXISTS trg_kb_chunks_ad AFTER DELETE ON kb_chunks BEGIN
    DELETE FROM kb_chunks_fts WHERE rowid = old.rowid;
END;
CREATE TRIGGER IF NOT EXISTS trg_kb_chunks_au AFTER UPDATE ON kb_chunks BEGIN
    DELETE FROM kb_chunks_fts WHERE rowid = old.rowid;
    INSERT INTO kb_chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;
"""


async def init_schema(db: Database) -> None:
    """Create all current tables, indexes, virtual tables, and triggers."""
    cursor = await db.connection.executescript(_SCHEMA)
    try:
        await db.connection.commit()
    finally:
        await cursor.close()


async def _recover_interrupted_tasks(db: Database) -> None:
    """Mark records left running by a previous process as interrupted."""
    await db.execute(
        "UPDATE task_logs SET status = 'interrupted' WHERE status = 'running'",
    )


async def _backfill_source_fts(db: Database) -> None:
    """Populate the source FTS index once when legacy content has no index rows."""
    source_count = await db.fetchone("SELECT COUNT(*) FROM source_data")
    fts_count = await db.fetchone("SELECT COUNT(*) FROM source_data_fts")
    if source_count is None or fts_count is None:
        return
    if int(source_count[0]) == 0 or int(fts_count[0]) > 0:
        return

    await db.execute(
        """
        INSERT INTO source_data_fts(rowid, title, description, ai_summary)
        SELECT rowid, title, description, COALESCE(json_extract(metadata, '$.ai_summary'), '')
        FROM source_data
        """,
    )


async def init_db(path: str) -> Database:
    """Open, initialize, repair, and return a ready SQLite database."""
    database = await Database.open(path)
    await init_schema(database)
    await _recover_interrupted_tasks(database)
    await _backfill_source_fts(database)
    return database
