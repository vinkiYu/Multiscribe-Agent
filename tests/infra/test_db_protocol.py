"""Contract tests for the backend-neutral database boundary."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from multiscribe_agent.infra.db import Database, SqliteDatabase
from multiscribe_agent.infra.db_protocol import DatabaseProtocol


def test_database_alias_points_to_sqlite_implementation() -> None:
    """Keep the historical Database import while exposing the explicit backend name."""
    assert Database is SqliteDatabase
    database = SqliteDatabase(connection=object())  # type: ignore[arg-type]
    assert isinstance(database, DatabaseProtocol)


@pytest.mark.asyncio
async def test_sqlite_rows_satisfy_protocol_mapping_contract() -> None:
    """SQLite rows remain runtime mappings behind the backend-neutral annotations."""
    database = await SqliteDatabase.open(":memory:", enable_sql_audit=False)
    try:
        await database.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)")
        await database.execute("INSERT INTO records(value) VALUES (?)", ("hello",))
        row = await database.fetchone("SELECT id, value FROM records")
        rows = await database.fetchall("SELECT id, value FROM records")
        assert row is not None
        assert isinstance(row, Mapping)
        assert rows
        assert all(isinstance(item, Mapping) for item in rows)
        assert row["value"] == "hello"
    finally:
        await database.close()
