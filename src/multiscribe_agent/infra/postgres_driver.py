"""Optional PostgreSQL database skeleton backed by ``asyncpg``."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from importlib import import_module
from typing import Any, Protocol

from multiscribe_agent.infra.db_protocol import PlaceholderStyle, SqlParameters

try:
    import_module("asyncpg")
except ImportError as exc:  # pragma: no cover - exercised when the optional extra is absent.
    message = (
        "asyncpg is required for the PostgreSQL backend. "
        "Install it with: pip install 'multiscribe-agent[postgres]'"
    )
    raise ImportError(message) from exc


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

    This Phase 1 skeleton exposes the common database contract only. Bootstrap,
    schema migration, and repository dialect conversion remain SQLite-only until
    subsequent migration phases wire them explicitly.
    """

    __slots__ = ("_audit_logger", "_pool")

    def __init__(self, pool: _AsyncpgPool) -> None:
        """Create a backend wrapper around an initialized asyncpg pool."""
        self._pool = pool
        self._audit_logger: object | None = None

    @property
    def placeholder_style(self) -> PlaceholderStyle:
        """PostgreSQL uses numbered ``$1`` placeholders."""
        return PlaceholderStyle.DOLLAR

    async def execute(self, statement: str, parameters: SqlParameters = ()) -> int:
        """Execute one statement and return the count encoded in its command tag."""
        async with self._pool.acquire() as connection:
            command_tag = await connection.execute(statement, *parameters)
        return _command_tag_count(command_tag)

    async def executemany(self, statement: str, parameters: list[SqlParameters]) -> int:
        """Execute one statement for every parameter set and return its batch size."""
        async with self._pool.acquire() as connection:
            await connection.executemany(statement, parameters)
        return len(parameters)

    async def fetchone(
        self, statement: str, parameters: SqlParameters = ()
    ) -> Mapping[str, Any] | None:
        """Return the first result row, if present."""
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(statement, *parameters)
        return AsyncpgRowMapping(row) if row is not None else None

    async def fetchall(
        self, statement: str, parameters: SqlParameters = ()
    ) -> list[Mapping[str, Any]]:
        """Return all result rows as backend-neutral mappings."""
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(statement, *parameters)
        return [AsyncpgRowMapping(row) for row in rows]

    async def close(self) -> None:
        """Close the underlying asyncpg pool."""
        await self._pool.close()

    def set_audit_logger(self, audit_logger: object | None) -> None:
        """Keep the protocol-compatible audit sink for later Postgres integration."""
        self._audit_logger = audit_logger


def _command_tag_count(command_tag: str) -> int:
    """Extract a trailing affected-row count from an asyncpg command tag."""
    try:
        return int(command_tag.rsplit(" ", maxsplit=1)[-1])
    except ValueError:
        return 0
