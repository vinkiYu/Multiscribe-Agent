"""Optional PostgreSQL database skeleton backed by ``asyncpg``."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from importlib import import_module
from typing import Any, Protocol, cast

import structlog

from multiscribe_agent.infra.db_protocol import SqlParameters

try:
    import_module("asyncpg")
except ImportError as exc:  # pragma: no cover - exercised when the runtime is incomplete.
    message = (
        "asyncpg is required for the PostgreSQL backend. "
        "Install the project runtime dependencies before starting the service."
    )
    raise ImportError(message) from exc

log = structlog.get_logger(__name__)


class _AsyncpgRecord(Protocol):
    """Subset of ``asyncpg.Record`` used by the backend-neutral row adapter."""

    def __getitem__(self, key: str) -> object:
        """Return a value by column name."""

    def keys(self) -> Sequence[str]:
        """Return column names in record order."""

    def values(self) -> Sequence[object]:
        """Return values in record order."""


class _AsyncpgConnection(Protocol):
    """Subset of an asyncpg connection required by the database skeleton."""

    async def execute(self, statement: str, *parameters: object) -> str:
        """Execute a statement and return its command tag."""

    async def executemany(self, statement: str, parameter_sets: Sequence[SqlParameters]) -> None:
        """Execute a statement for all parameter sets."""

    async def fetchrow(self, statement: str, *parameters: object) -> _AsyncpgRecord | None:
        """Fetch one record."""

    async def fetch(self, statement: str, *parameters: object) -> Sequence[_AsyncpgRecord]:
        """Fetch all records."""

    async def fetchval(self, statement: str, *parameters: object) -> object:
        """Fetch one scalar value from a statement returning a value."""


class _AsyncpgPool(Protocol):
    """Subset of an asyncpg pool required by the database skeleton."""

    def acquire(self) -> AbstractAsyncContextManager[_AsyncpgConnection]:
        """Acquire a connection from the pool."""

    async def close(self) -> None:
        """Close the pool."""


class AsyncpgRowMapping(Mapping[str, Any]):
    """Adapt ``asyncpg.Record`` to the repository row mapping contract."""

    def __init__(self, record: _AsyncpgRecord) -> None:
        """Copy one record while retaining legacy positional lookup support."""
        self._data = dict(zip(record.keys(), record.values(), strict=True))
        self._values = tuple(record.values())

    def __getitem__(self, key: str | int) -> Any:  # noqa: ANN401 - database values are dynamic.
        """Read a column by name or a legacy positional index."""
        if isinstance(key, int):
            return self._values[key]
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        """Iterate column names in record order."""
        return iter(self._data)

    def __len__(self) -> int:
        """Return the number of values in the record."""
        return len(self._data)


class PostgresDatabase:
    """PostgreSQL implementation of :class:`DatabaseProtocol` using ``asyncpg``.

    The driver exposes the common database contract and the migrations required
    by the daily-digest idempotency and workflow-resume paths.
    """

    __slots__ = (
        "_audit_logger",
        "_enable_sql_audit",
        "_metrics_registry_provider",
        "_pool",
        "_slow_query_threshold",
    )

    def __init__(
        self,
        pool: _AsyncpgPool,
        *,
        slow_query_threshold: float = 1.0,
        enable_sql_audit: bool = True,
        metrics_registry_provider: Callable[[], Any] | None = None,
    ) -> None:
        """Create a backend wrapper around an initialized asyncpg pool.

        ``metrics_registry_provider`` overrides the global metrics registry
        lookup; tests inject it to stay independent of module import order.
        """
        self._pool = pool
        self._audit_logger: object | None = None
        self._slow_query_threshold = slow_query_threshold
        self._enable_sql_audit = enable_sql_audit
        self._metrics_registry_provider = metrics_registry_provider

    async def execute(self, statement: str, parameters: SqlParameters = ()) -> int | None:
        """Execute one statement and return its row count or RETURNING value."""
        started = time.monotonic()
        async with self._pool.acquire() as connection:
            if " RETURNING " in statement.upper():
                value = await connection.fetchval(statement, *parameters)
                self._record_query_observability(statement, parameters, time.monotonic() - started)
                await self._audit_write(statement, parameters)
                return cast(int | None, value)
            command_tag = await connection.execute(statement, *parameters)
        duration = time.monotonic() - started
        self._record_query_observability(statement, parameters, duration)
        await self._audit_write(statement, parameters)
        return _command_tag_count(command_tag)

    async def executemany(self, statement: str, parameters: Sequence[SqlParameters]) -> int:
        """Execute one statement for every parameter set and return its batch size."""
        started = time.monotonic()
        async with self._pool.acquire() as connection:
            await connection.executemany(statement, parameters)
        self._record_query_observability(statement, parameters, time.monotonic() - started)
        await self._audit_write(statement, parameters)
        return len(parameters)

    async def fetchone(
        self, statement: str, parameters: SqlParameters = ()
    ) -> Mapping[str, Any] | None:
        """Return the first result row, if present."""
        started = time.monotonic()
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(statement, *parameters)
        self._record_query_observability(statement, parameters, time.monotonic() - started)
        return AsyncpgRowMapping(row) if row is not None else None

    async def fetchall(
        self, statement: str, parameters: SqlParameters = ()
    ) -> list[Mapping[str, Any]]:
        """Return all result rows as backend-neutral mappings."""
        started = time.monotonic()
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(statement, *parameters)
        self._record_query_observability(statement, parameters, time.monotonic() - started)
        return [AsyncpgRowMapping(row) for row in rows]

    async def close(self) -> None:
        """Close the underlying asyncpg pool."""
        await self._pool.close()

    async def migrate_daily_digest(self) -> None:
        """Create daily-digest deduplication, history, and iteration tables."""
        from multiscribe_agent.infra.postgres.schema_dedup import ALL_SCHEMAS

        for schema in ALL_SCHEMAS:
            for statement in schema.split(";"):
                statement = statement.strip()
                if statement:
                    await self.execute(statement)

    async def migrate_daily_digest_archives(self) -> None:
        """Upgrade a pre-P41 archive table with the approval-status column."""
        await self.execute(
            """
            ALTER TABLE daily_digest_archives
            ADD COLUMN IF NOT EXISTS approval_status TEXT NOT NULL DEFAULT 'published'
            """
        )

    async def migrate_rag_index_registry(self) -> None:
        """Create the PostgreSQL RAG index manifest and its lookup indexes."""
        from multiscribe_agent.infra.postgres.schema_rag import (
            RAG_INDEX_REGISTRY_INDEXES,
            RAG_INDEX_REGISTRY_TABLE,
        )

        await self.execute(RAG_INDEX_REGISTRY_TABLE)
        for statement in RAG_INDEX_REGISTRY_INDEXES:
            await self.execute(statement)

    def set_audit_logger(self, audit_logger: object | None) -> None:
        """Attach the audit sink used by :meth:`_audit_write` for write statements."""
        self._audit_logger = audit_logger

    async def _audit_write(
        self, statement: str, parameters: SqlParameters | Sequence[SqlParameters]
    ) -> None:
        """Send write statements to the audit sink without affecting the caller."""
        if (
            not self._enable_sql_audit
            or self._audit_logger is None
            or not _is_write_statement(statement)
            or "SQL_AUDIT_LOG" in statement.upper()
        ):
            return
        try:
            audit_record = cast(Any, self._audit_logger).record
            await audit_record(statement, parameters)
        except Exception as exc:  # auditing must never break the write path.
            log.warning(
                "sql_audit_failed",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )

    def _record_query_observability(
        self,
        statement: str,
        parameters: SqlParameters | Sequence[SqlParameters],
        duration: float,
    ) -> None:
        """Emit slow-query warnings and update the optional metric backend."""
        try:
            if self._metrics_registry_provider is not None:
                registry = self._metrics_registry_provider()
            else:
                from multiscribe_agent.observability.meter import get_metrics_registry

                registry = get_metrics_registry()
            record_query_timing = getattr(registry, "record_query_timing", None)
            if callable(record_query_timing):
                record_query_timing(duration, self._slow_query_threshold)
            elif duration >= self._slow_query_threshold:
                # Compatibility for test/deployment registries from before P43.
                record_slow_query = getattr(registry, "record_slow_query", None)
                if callable(record_slow_query):
                    record_slow_query(duration)
                else:
                    record_counter = getattr(registry, "_record_counter", None)
                    if callable(record_counter):
                        record_counter("slow_query")
        except (ImportError, RuntimeError, TypeError, AttributeError):
            log.debug("slow_query_metric_unavailable")

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


def _command_tag_count(command_tag: str) -> int:
    """Extract a trailing affected-row count from an asyncpg command tag."""
    try:
        return int(command_tag.rsplit(" ", maxsplit=1)[-1])
    except ValueError:
        return 0


def _is_write_statement(statement: str) -> bool:
    """Return whether a statement is one of the audited SQL write operations."""
    return statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
