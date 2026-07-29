"""Repository dialect routing and JSON expression coverage."""

from __future__ import annotations

from multiscribe_agent.infra.db_protocol import PlaceholderStyle
from multiscribe_agent.infra.dialect import (
    DialectRepositoryMixin,
    PgDialect,
    SqlDialect,
    dialect_for,
)


class _SqliteBackend:
    placeholder_style = PlaceholderStyle.QUESTION_MARK


class _PostgresBackend:
    placeholder_style = PlaceholderStyle.DOLLAR


class _Repository(DialectRepositoryMixin):
    def __init__(self, database: object) -> None:
        self._db = database


def test_dialect_passthrough_and_selection() -> None:
    """SQLite keeps question marks while PostgreSQL receives numbered binds."""
    assert isinstance(dialect_for(_SqliteBackend()), SqlDialect)
    assert isinstance(dialect_for(_PostgresBackend()), PgDialect)
    assert SqlDialect().translate("SELECT ?") == "SELECT ?"
    assert PgDialect().translate("SELECT '?' AS literal, ?") == "SELECT '?' AS literal, $1"


def test_json_expression_follows_database_dialect() -> None:
    """Trusted JSON scalar extraction uses equivalent backend syntax."""
    sqlite = _Repository(_SqliteBackend())
    postgres = _Repository(_PostgresBackend())
    assert sqlite._json_extract("data", "sha256") == "json_extract(data, '$.sha256')"
    assert postgres._json_extract("data", "sha256") == "data->>'sha256'"
