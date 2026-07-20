"""SQLite connection management, schema initialization, and FTS indexes."""

from __future__ import annotations

import importlib
import time
from collections.abc import Iterable, Sequence
from contextvars import ContextVar
from typing import TYPE_CHECKING, Protocol, cast

import aiosqlite
import structlog

if TYPE_CHECKING:
    from multiscribe_agent.infra.connection_pool import ConnectionPool
    from multiscribe_agent.observability.sql_audit import AuditEntry, SqlAuditLogger

type SqlParameters = Sequence[object]
log = structlog.get_logger(__name__)
_active_write_connection: ContextVar[aiosqlite.Connection | None] = ContextVar(
    "active_write_connection", default=None
)


class _AuditLogger(Protocol):
    """Minimal audit sink accepted by the database wrapper."""

    async def record(self, statement: str, parameters: SqlParameters) -> AuditEntry:
        """Record one write statement."""


class _SqliteVecModule(Protocol):
    """Minimal sqlite-vec module API used to locate its loadable extension."""

    def loadable_path(self) -> str: ...


class Database:
    """Wrap an aiosqlite connection with small typed query helpers."""

    def __init__(
        self,
        connection: aiosqlite.Connection | None = None,
        *,
        pool: ConnectionPool | None = None,
        slow_query_threshold: float = 1.0,
        enable_sql_audit: bool = True,
    ) -> None:
        """Create a database wrapper around an open connection."""
        if slow_query_threshold <= 0:
            raise ValueError("slow_query_threshold must be positive")
        if connection is None and pool is None:
            raise ValueError("Database requires a connection or pool")
        self._pool = pool
        self.connection = connection if connection is not None else pool.write_connection  # type: ignore[union-attr]
        self._slow_query_threshold = slow_query_threshold
        self._enable_sql_audit = enable_sql_audit
        self._audit_logger: _AuditLogger | None = None

    @classmethod
    async def open(
        cls,
        path: str,
        *,
        slow_query_threshold: float = 1.0,
        enable_sql_audit: bool = True,
    ) -> Database:
        """Open a database connection and apply SQLite runtime settings."""
        connection = await aiosqlite.connect(path)
        connection.row_factory = aiosqlite.Row
        database = cls(
            connection,
            slow_query_threshold=slow_query_threshold,
            enable_sql_audit=enable_sql_audit,
        )
        await database._configure()
        return database

    @classmethod
    async def open_with_pool(
        cls,
        path: str,
        *,
        read_pool_size: int = 5,
        write_timeout: float = 30.0,
        slow_query_threshold: float = 1.0,
        enable_sql_audit: bool = True,
    ) -> Database:
        """Open a file-backed database using separate read and write lanes."""
        from multiscribe_agent.infra.connection_pool import ConnectionPool

        pool = ConnectionPool(
            path,
            read_pool_size=read_pool_size,
            write_timeout=write_timeout,
        )
        await pool.initialize()
        return cls(
            pool=pool,
            slow_query_threshold=slow_query_threshold,
            enable_sql_audit=enable_sql_audit,
        )

    def set_audit_logger(self, audit_logger: SqlAuditLogger | None) -> None:
        """Attach the audit sink used for subsequent write statements."""
        self._audit_logger = audit_logger

    async def close(self) -> None:
        """Close the underlying SQLite connection."""
        if self._pool is not None:
            await self._pool.close()
        else:
            await self.connection.close()

    async def execute(self, statement: str, parameters: SqlParameters = ()) -> int:
        """Execute one write statement, commit it, and return affected rows."""
        active_connection = _active_write_connection.get()
        if active_connection is not None:
            return await self._execute_on_connection(active_connection, statement, parameters)
        if self._pool is not None:
            async with self._pool.acquire_write() as connection:
                return await self._execute_on_connection(connection, statement, parameters)
        return await self._execute_on_connection(self.connection, statement, parameters)

    async def _execute_on_connection(
        self,
        connection: aiosqlite.Connection,
        statement: str,
        parameters: SqlParameters,
    ) -> int:
        """Run one write on a selected lane and apply observability hooks."""
        started = time.monotonic()
        cursor = await connection.execute(statement, parameters)
        try:
            await connection.commit()
            return cursor.rowcount
        finally:
            await cursor.close()
            self._record_query_observability(statement, parameters, time.monotonic() - started)
            token = _active_write_connection.set(connection)
            try:
                await self._audit_write(statement, parameters)
                await self._sync_tokenized_fts(connection, statement, parameters)
            finally:
                _active_write_connection.reset(token)

    async def executemany(
        self,
        statement: str,
        parameter_sets: Iterable[SqlParameters],
    ) -> int:
        """Execute a batch write and return the number of database changes."""
        if self._pool is not None:
            async with self._pool.acquire_write() as connection:
                return await self._executemany_on_connection(connection, statement, parameter_sets)
        return await self._executemany_on_connection(self.connection, statement, parameter_sets)

    async def _executemany_on_connection(
        self,
        connection: aiosqlite.Connection,
        statement: str,
        parameter_sets: Iterable[SqlParameters],
    ) -> int:
        """Run a batch write on a selected lane."""
        started = time.monotonic()
        materialized = list(parameter_sets)
        changes_before = connection.total_changes
        cursor = await connection.executemany(statement, materialized)
        try:
            await connection.commit()
            return connection.total_changes - changes_before
        finally:
            await cursor.close()
            self._record_query_observability(statement, (), time.monotonic() - started)
            token = _active_write_connection.set(connection)
            try:
                for parameters in materialized:
                    await self._audit_write(statement, parameters)
            finally:
                _active_write_connection.reset(token)

    async def fetchone(
        self,
        statement: str,
        parameters: SqlParameters = (),
    ) -> aiosqlite.Row | None:
        """Return the first row for a parameterized query."""
        if self._pool is not None:
            async with self._pool.acquire_read() as connection:
                return await self._fetchone_on_connection(connection, statement, parameters)
        return await self._fetchone_on_connection(self.connection, statement, parameters)

    async def _fetchone_on_connection(
        self,
        connection: aiosqlite.Connection,
        statement: str,
        parameters: SqlParameters,
    ) -> aiosqlite.Row | None:
        """Fetch one row on a selected read lane."""
        started = time.monotonic()
        normalized_parameters = self._normalize_fts_parameters(statement, parameters)
        cursor = await connection.execute(statement, normalized_parameters)
        try:
            return await cursor.fetchone()
        finally:
            await cursor.close()
            self._record_query_observability(statement, parameters, time.monotonic() - started)

    async def fetchall(
        self,
        statement: str,
        parameters: SqlParameters = (),
    ) -> list[aiosqlite.Row]:
        """Return all rows for a parameterized query."""
        if self._pool is not None:
            async with self._pool.acquire_read() as connection:
                return await self._fetchall_on_connection(connection, statement, parameters)
        return await self._fetchall_on_connection(self.connection, statement, parameters)

    async def _fetchall_on_connection(
        self,
        connection: aiosqlite.Connection,
        statement: str,
        parameters: SqlParameters,
    ) -> list[aiosqlite.Row]:
        """Fetch all rows on a selected read lane."""
        started = time.monotonic()
        normalized_parameters = self._normalize_fts_parameters(statement, parameters)
        cursor = await connection.execute(statement, normalized_parameters)
        try:
            return list(await cursor.fetchall())
        finally:
            await cursor.close()
            self._record_query_observability(statement, parameters, time.monotonic() - started)

    async def _audit_write(self, statement: str, parameters: SqlParameters) -> None:
        """Send write statements to the audit sink without affecting the caller."""
        if (
            not self._enable_sql_audit
            or self._audit_logger is None
            or not self._is_write_statement(statement)
            or "SQL_AUDIT_LOG" in statement.upper()
        ):
            return
        try:
            await self._audit_logger.record(statement, parameters)
        except (aiosqlite.Error, OSError, RuntimeError, TypeError, ValueError) as exc:
            log.warning("sql_audit_failed", error_type=type(exc).__name__, error=str(exc))

    def _record_query_observability(
        self, statement: str, parameters: SqlParameters, duration: float
    ) -> None:
        """Emit slow-query warning and update the optional metric backend."""
        if duration < self._slow_query_threshold:
            return
        parameter_count = len(parameters) if hasattr(parameters, "__len__") else 0
        log.warning(
            "slow_query",
            statement=statement[:200],
            param_count=parameter_count,
            duration_ms=round(duration * 1000, 2),
            threshold_ms=round(self._slow_query_threshold * 1000, 2),
        )
        try:
            from multiscribe_agent.observability.meter import get_metrics_registry

            registry = get_metrics_registry()
            record_slow_query = getattr(registry, "record_slow_query", None)
            if callable(record_slow_query):
                record_slow_query(duration)
            else:
                record_counter = getattr(registry, "_record_counter", None)
                if callable(record_counter):
                    record_counter("slow_query")
        except (ImportError, RuntimeError, TypeError):
            log.debug("slow_query_metric_unavailable")

    @staticmethod
    def _is_write_statement(statement: str) -> bool:
        """Return whether a statement is one of the audited SQL write operations."""
        return statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))

    @staticmethod
    def _normalize_fts_parameters(statement: str, parameters: SqlParameters) -> SqlParameters:
        """Apply the same tokenizer to FTS query parameters as to indexed text."""
        upper = statement.upper()
        if " MATCH ?" not in upper or not any(
            name in upper for name in ("_FTS", "FTS5", "SOURCE_DATA_FTS", "AGENT_MEMORIES_FTS")
        ):
            return parameters
        if not parameters or not isinstance(parameters[0], str):
            return parameters
        from multiscribe_agent.infra.text_tokenize import tokenize_for_fts

        return (tokenize_for_fts(parameters[0]), *parameters[1:])

    async def _sync_tokenized_fts(
        self,
        connection: aiosqlite.Connection,
        statement: str,
        parameters: SqlParameters,
    ) -> None:
        """Replace the raw kb chunk trigger row with jieba-tokenized content."""
        upper = statement.upper()
        if "INSERT INTO KB_CHUNKS" not in upper or not parameters:
            return
        chunk_id = parameters[0]
        if not isinstance(chunk_id, str):
            return
        try:
            from multiscribe_agent.infra.text_tokenize import tokenize_for_fts

            cursor = await connection.execute(
                "SELECT rowid, content FROM kb_chunks WHERE id = ?", (chunk_id,)
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row is None:
                return
            update = await connection.execute(
                "UPDATE kb_chunks_fts SET content = ? WHERE rowid = ?",
                (tokenize_for_fts(str(row["content"])), int(row["rowid"])),
            )
            await update.close()
            await connection.commit()
        except (ImportError, aiosqlite.Error, KeyError, TypeError, ValueError):
            return

    async def migrate_publish_history(self) -> None:
        """Create the publisher outcome table and its bounded-query indexes."""
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS publish_history (
                id TEXT PRIMARY KEY,
                publisher_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('success', 'error')),
                title TEXT NOT NULL,
                content_preview TEXT NOT NULL,
                result_data TEXT NOT NULL DEFAULT '{}',
                error_message TEXT,
                published_at TEXT NOT NULL,
                adapter_name TEXT
            )
            """,
        )
        await self.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_publish_history_publisher_published
            ON publish_history(publisher_id, published_at DESC)
            """,
        )
        await self.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_publish_history_published
            ON publish_history(published_at DESC)
            """,
        )

    async def migrate_kb(self) -> bool:
        """Create durable KB indexes and enable sqlite-vec when its optional extension exists."""
        await self.connection.executescript(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS kb_documents_fts USING fts5(name, summary, body);
            CREATE TRIGGER IF NOT EXISTS trg_kb_documents_ai AFTER INSERT ON kb_documents BEGIN
                INSERT INTO kb_documents_fts(rowid, name, summary, body)
                VALUES (
                    new.rowid,
                    COALESCE(json_extract(new.data, '$.name'), ''),
                    COALESCE(json_extract(new.data, '$.summary'), ''),
                    ''
                );
            END;
            CREATE TRIGGER IF NOT EXISTS trg_kb_documents_ad AFTER DELETE ON kb_documents BEGIN
                DELETE FROM kb_documents_fts WHERE rowid = old.rowid;
            END;
            CREATE TRIGGER IF NOT EXISTS trg_kb_documents_au AFTER UPDATE ON kb_documents BEGIN
                DELETE FROM kb_documents_fts WHERE rowid = old.rowid;
                INSERT INTO kb_documents_fts(rowid, name, summary, body)
                VALUES (
                    new.rowid,
                    COALESCE(json_extract(new.data, '$.name'), ''),
                    COALESCE(json_extract(new.data, '$.summary'), ''),
                    ''
                );
            END;
            CREATE INDEX IF NOT EXISTS idx_kb_documents_category ON kb_documents(category_id);
            CREATE INDEX IF NOT EXISTS idx_kb_chunks_document ON kb_chunks(document_id);
            CREATE TABLE IF NOT EXISTS kb_chunk_dedup (
                content_hash TEXT PRIMARY KEY,
                chunk_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_kb_chunk_dedup_chunk ON kb_chunk_dedup(chunk_id);
            """
        )
        await self.connection.commit()
        try:
            module = importlib.import_module("sqlite_vec")
            sqlite_vec = cast(_SqliteVecModule, module)

            await self.connection.enable_load_extension(True)
            await self.connection.load_extension(sqlite_vec.loadable_path())
            await self.connection.enable_load_extension(False)
            await self.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_vec USING vec0("
                "chunk_id TEXT PRIMARY KEY, embedding float[384])"
            )
        except (ImportError, OSError, aiosqlite.Error):
            return False
        return True

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

CREATE TABLE IF NOT EXISTS workflow_iterations (
    workflow_run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    round INTEGER NOT NULL,
    output TEXT NOT NULL DEFAULT '',
    score REAL,
    feedback TEXT,
    converged INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    recorded_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    PRIMARY KEY (workflow_run_id, step_id, round)
);
CREATE INDEX IF NOT EXISTS idx_workflow_iterations_run
    ON workflow_iterations(workflow_run_id);

CREATE TABLE IF NOT EXISTS sql_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    statement TEXT NOT NULL,
    operation TEXT NOT NULL,
    param_count INTEGER NOT NULL DEFAULT 0,
    suspicious INTEGER NOT NULL DEFAULT 0,
    suspicious_patterns TEXT NOT NULL DEFAULT '',
    recorded_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sql_audit_suspicious ON sql_audit_log(suspicious);
CREATE INDEX IF NOT EXISTS idx_sql_audit_recorded_at ON sql_audit_log(recorded_at);

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

CREATE TABLE IF NOT EXISTS interop_keys (
    key_id TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    approved INTEGER NOT NULL DEFAULT 0,
    rate_limit_per_minute INTEGER NOT NULL DEFAULT 60,
    last_used_at INTEGER,
    request_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_interop_keys_approved ON interop_keys(approved);

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


async def init_db(
    path: str,
    *,
    slow_query_threshold: float = 1.0,
    enable_sql_audit: bool = True,
    use_pool: bool = False,
    read_pool_size: int = 5,
) -> Database:
    """Open, initialize, repair, and return a ready SQLite database."""
    if use_pool and path != ":memory:":
        database = await Database.open_with_pool(
            path,
            read_pool_size=read_pool_size,
            slow_query_threshold=slow_query_threshold,
            enable_sql_audit=enable_sql_audit,
        )
    else:
        database = await Database.open(
            path,
            slow_query_threshold=slow_query_threshold,
            enable_sql_audit=enable_sql_audit,
        )
    await init_schema(database)
    await database.migrate_publish_history()
    await database.migrate_kb()
    await _recover_interrupted_tasks(database)
    await _backfill_source_fts(database)
    return database
