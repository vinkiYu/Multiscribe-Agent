"""Regression tests for the PostgreSQL repository helper."""

from __future__ import annotations

from multiscribe_agent.infra.db_protocol import PostgresRepositoryMixin


class _Repository(PostgresRepositoryMixin):
    _db = object()


def test_repository_sql_translates_to_postgres_binds() -> None:
    """Repositories expose one-way PostgreSQL bind translation only."""
    assert _Repository._sql("SELECT '?' AS literal, ?") == "SELECT '?' AS literal, $1"


def test_json_expression_uses_postgres_jsonb_operator() -> None:
    """Trusted JSON scalar extraction uses PostgreSQL's JSONB operator."""
    assert _Repository._json_extract("data", "sha256") == "data->>'sha256'"
