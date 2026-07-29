"""Smoke tests for the optional asyncpg backend skeleton."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from types import ModuleType
from typing import Any

import pytest

from multiscribe_agent.domain.models import TaskLog
from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.db_protocol import DatabaseProtocol, PlaceholderStyle
from multiscribe_agent.infra.repositories.task_log import TaskLogRepository

MODULE_NAME = "multiscribe_agent.infra.postgres_driver"


def _load_fake_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Load the driver with a fake asyncpg module installed."""
    monkeypatch.delitem(sys.modules, MODULE_NAME, raising=False)
    monkeypatch.setitem(sys.modules, "asyncpg", ModuleType("asyncpg"))
    return importlib.import_module(MODULE_NAME)


class _FakeRecord:
    """Minimal asyncpg record substitute for mapping adaptation tests."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def keys(self) -> Sequence[str]:
        return tuple(self._data)

    def values(self) -> Sequence[Any]:
        return tuple(self._data.values())


class _FakeConnection:
    """Minimal asyncpg connection substitute that records bound parameters."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.returning_value: object | None = 42

    async def execute(self, statement: str, *parameters: Any) -> str:
        self.calls.append((statement, parameters))
        return "INSERT 0 1"

    async def executemany(self, statement: str, parameter_sets: Sequence[Sequence[Any]]) -> None:
        self.calls.append((statement, tuple(parameter_sets)))

    async def fetchrow(self, statement: str, *parameters: Any) -> _FakeRecord | None:
        self.calls.append((statement, parameters))
        return _FakeRecord({"id": 1, "title": "one"})

    async def fetch(self, statement: str, *parameters: Any) -> Sequence[_FakeRecord]:
        self.calls.append((statement, parameters))
        return (_FakeRecord({"id": 2, "title": "two"}),)

    async def fetchval(self, statement: str, *parameters: Any) -> object:
        self.calls.append((statement, parameters))
        return self.returning_value


class _FakeAcquire(AbstractAsyncContextManager[_FakeConnection]):
    """Async context manager returned by a fake pool acquisition."""

    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> _FakeConnection:
        return self._connection

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: Any
    ) -> None:
        return None


class _FakePool:
    """Minimal asyncpg pool substitute."""

    def __init__(self) -> None:
        self.connection = _FakeConnection()
        self.closed = False

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(self.connection)

    async def close(self) -> None:
        self.closed = True


def test_postgres_driver_missing_optional_dependency_has_install_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An absent asyncpg package raises a controlled ImportError at import time."""
    monkeypatch.delitem(sys.modules, MODULE_NAME, raising=False)
    monkeypatch.delitem(sys.modules, "asyncpg", raising=False)

    with pytest.raises(ImportError, match="asyncpg is required"):
        importlib.import_module(MODULE_NAME)


@pytest.mark.asyncio
async def test_postgres_database_implements_protocol_with_fake_asyncpg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The skeleton exposes the complete protocol without installing asyncpg."""
    module = _load_fake_module(monkeypatch)
    pool = _FakePool()
    database = module.PostgresDatabase(pool)

    assert isinstance(database, DatabaseProtocol)
    assert database.placeholder_style is PlaceholderStyle.DOLLAR
    assert await database.execute("INSERT INTO records(value) VALUES ($1)", ("value",)) == 1
    assert pool.connection.calls[-1] == ("INSERT INTO records(value) VALUES ($1)", ("value",))

    assert (
        await database.executemany("INSERT INTO records(value) VALUES ($1)", [("a",), ("b",)]) == 2
    )
    row = await database.fetchone("SELECT id, title FROM records WHERE id = $1", (1,))
    rows = await database.fetchall("SELECT id, title FROM records")
    assert row is not None
    assert row["title"] == "one"
    assert rows[0][0] == 2

    await database.close()
    assert pool.closed


@pytest.mark.asyncio
async def test_sqlite_execute_with_returning(db: Database) -> None:
    """SQLite extracts an inserted id from a RETURNING clause."""
    await db.execute("CREATE TABLE returning_records (id INTEGER PRIMARY KEY AUTOINCREMENT)")
    row_id = await db.execute("INSERT INTO returning_records DEFAULT VALUES RETURNING id")

    assert row_id == 1


@pytest.mark.asyncio
async def test_sqlite_execute_without_returning(db: Database) -> None:
    """SQLite retains affected-row semantics for ordinary DML."""
    await db.execute("CREATE TABLE rowcount_records (id INTEGER PRIMARY KEY, value TEXT)")
    affected = await db.execute("INSERT INTO rowcount_records(id, value) VALUES (?, ?)", (1, "one"))

    assert affected == 1


@pytest.mark.asyncio
async def test_postgres_execute_returning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Postgres uses one fetchval call for a RETURNING statement."""
    module = _load_fake_module(monkeypatch)
    pool = _FakePool()
    database = module.PostgresDatabase(pool)

    assert (
        await database.execute("INSERT INTO records(value) VALUES ($1) RETURNING id", ("value",))
        == 42
    )
    assert pool.connection.calls == [
        ("INSERT INTO records(value) VALUES ($1) RETURNING id", ("value",))
    ]


@pytest.mark.asyncio
async def test_postgres_execute_rowcount(monkeypatch: pytest.MonkeyPatch) -> None:
    """Postgres uses the command tag for ordinary statements."""
    module = _load_fake_module(monkeypatch)
    pool = _FakePool()
    database = module.PostgresDatabase(pool)

    assert await database.execute("DELETE FROM records WHERE id = $1", (1,)) == 1
    assert pool.connection.calls == [("DELETE FROM records WHERE id = $1", (1,))]


@pytest.mark.asyncio
async def test_task_log_create_via_protocol() -> None:
    """Task log creation does not depend on a backend connection attribute."""

    class ProtocolDatabase:
        async def execute(self, statement: str, parameters: tuple[object, ...] = ()) -> int:
            del parameters
            assert "RETURNING id" in statement
            return 7

        @property
        def connection(self) -> object:
            raise AssertionError("TaskLogRepository must not access db.connection")

    log = TaskLog(
        task_id="task-1",
        task_name="daily",
        start_time="2026-07-29T00:00:00Z",
        status="running",
    )

    assert await TaskLogRepository(ProtocolDatabase()).create(log) == "7"


@pytest.mark.asyncio
async def test_task_log_create_returns_string_id() -> None:
    """A protocol-backed task log repository returns the generated id as text."""

    class ProtocolDatabase:
        async def execute(self, statement: str, parameters: tuple[object, ...] = ()) -> int:
            del parameters
            assert "RETURNING id" in statement
            return 19

    log = TaskLog(
        task_id="task-2",
        task_name="daily",
        start_time="2026-07-29T00:00:00Z",
        status="success",
    )

    result = await TaskLogRepository(ProtocolDatabase()).create(log)

    assert result == "19"
