"""Repository-level SQL dialect helpers for the SQLite to PostgreSQL migration."""

from __future__ import annotations

from multiscribe_agent.infra.placeholder import (
    DOLLAR,
    QUESTION_MARK,
    PlaceholderGenerator,
    translate_question_marks,
)


class SqlDialect:
    """Render SQL for SQLite without changing existing question-mark binds."""

    placeholder: PlaceholderGenerator = QUESTION_MARK

    def translate(self, sql: str) -> str:
        """Return SQLite SQL unchanged."""
        return sql


class PgDialect:
    """Render SQLite-shaped SQL with PostgreSQL numbered bind parameters."""

    placeholder: PlaceholderGenerator = DOLLAR

    def translate(self, sql: str) -> str:
        """Translate question-mark binds while preserving quoted literals."""
        return translate_question_marks(sql, target="dollar")


def dialect_for(database: object) -> SqlDialect | PgDialect:
    """Select a dialect from a backend's ``placeholder_style`` marker."""
    style = getattr(database, "placeholder_style", None)
    if getattr(style, "value", None) == "dollar":
        return PgDialect()
    return SqlDialect()
