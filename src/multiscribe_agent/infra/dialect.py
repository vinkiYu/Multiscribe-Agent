"""Repository-level SQL dialect helpers for the SQLite to PostgreSQL migration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from multiscribe_agent.infra.db_protocol import DatabaseProtocol, SqlParameters
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


class DialectRepositoryMixin:
    """Translate repository SQL against the database currently bound to ``_db``."""

    _db: DatabaseProtocol

    @property
    def _dialect(self) -> SqlDialect | PgDialect:
        """Resolve the active dialect lazily so database rebinding is supported."""
        return dialect_for(self._db)

    async def _execute(
        self, statement: str, parameters: tuple[Any, ...] | list[Any] = ()
    ) -> int | None:
        """Execute one translated statement."""
        return await self._db.execute(self._dialect.translate(statement), parameters)

    async def _executemany(self, statement: str, parameters: list[tuple[object, ...]]) -> int:
        """Execute a translated statement for a batch of parameter sets."""
        return await self._db.executemany(
            self._dialect.translate(statement), cast(list[SqlParameters], parameters)
        )

    async def _fetchone(
        self, statement: str, parameters: tuple[Any, ...] | list[Any] = ()
    ) -> Mapping[str, Any] | None:
        """Fetch one row from a translated statement."""
        return await self._db.fetchone(self._dialect.translate(statement), parameters)

    async def _fetchall(
        self, statement: str, parameters: tuple[Any, ...] | list[Any] = ()
    ) -> list[Mapping[str, Any]]:
        """Fetch all rows from a translated statement."""
        return await self._db.fetchall(self._dialect.translate(statement), parameters)

    def _json_extract(self, column: str, path: str) -> str:
        """Render a trusted JSON scalar extraction for the active SQL dialect."""
        if not column.replace("_", "").isalnum() or not path.replace("_", "").isalnum():
            raise ValueError("JSON extraction identifiers must be trusted names")
        if isinstance(self._dialect, PgDialect):
            return f"{column}->>'{path}'"
        return f"json_extract({column}, '$.{path}')"


class ExplicitDatabaseDialectMixin:
    """Translate SQL for services whose legacy API receives ``db`` per call."""

    @staticmethod
    def _dialect_for(db: DatabaseProtocol) -> SqlDialect | PgDialect:
        """Resolve a dialect from an explicitly supplied database."""
        return dialect_for(db)

    async def _execute(
        self, db: DatabaseProtocol, statement: str, parameters: tuple[Any, ...] | list[Any] = ()
    ) -> int | None:
        """Execute one translated statement against an explicit database."""
        dialect = self._dialect_for(db)
        return await db.execute(dialect.translate(statement), parameters)

    async def _fetchone(
        self, db: DatabaseProtocol, statement: str, parameters: tuple[Any, ...] | list[Any] = ()
    ) -> Mapping[str, Any] | None:
        """Fetch one row from a translated statement against an explicit database."""
        dialect = self._dialect_for(db)
        return await db.fetchone(dialect.translate(statement), parameters)

    async def _fetchall(
        self, db: DatabaseProtocol, statement: str, parameters: tuple[Any, ...] | list[Any] = ()
    ) -> list[Mapping[str, Any]]:
        """Fetch all rows from a translated statement against an explicit database."""
        dialect = self._dialect_for(db)
        return await db.fetchall(dialect.translate(statement), parameters)
