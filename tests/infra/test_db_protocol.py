"""Contract tests for the PostgreSQL database boundary."""

from __future__ import annotations

from collections.abc import Sequence

from multiscribe_agent.infra.db import Database, PostgresDatabase
from multiscribe_agent.infra.db_protocol import DatabaseProtocol
from multiscribe_agent.infra.postgres_driver import AsyncpgRowMapping


def test_database_alias_points_to_postgres_implementation() -> None:
    """The stable Database import is now the PostgreSQL implementation."""
    assert Database is PostgresDatabase


def test_postgres_driver_exposes_protocol_contract() -> None:
    """The concrete driver and protocol remain importable from stable paths."""
    assert isinstance(PostgresDatabase, type)
    assert isinstance(DatabaseProtocol, type)


class _Record:
    def keys(self) -> Sequence[str]:
        return ("id", "value")

    def values(self) -> Sequence[object]:
        return (1, "hello")

    def __getitem__(self, key: str) -> object:
        return {"id": 1, "value": "hello"}[key]


def test_asyncpg_row_mapping_supports_named_and_positional_access() -> None:
    """Rows preserve both repository mapping access and positional compatibility."""
    row = AsyncpgRowMapping(_Record())
    assert row["value"] == "hello"
    assert row[1] == "hello"
    assert dict(row) == {"id": 1, "value": "hello"}
