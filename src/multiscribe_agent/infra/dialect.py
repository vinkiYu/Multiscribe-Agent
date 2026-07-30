"""Repository-level SQL dialect helpers for the SQLite to PostgreSQL migration."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any, cast

from multiscribe_agent.infra.db_protocol import DatabaseProtocol, SqlParameters
from multiscribe_agent.infra.placeholder import (
    DOLLAR,
    QUESTION_MARK,
    PlaceholderGenerator,
    translate_question_marks,
)


class UpsertStyle(Enum):
    """Supported insert conflict strategies across database dialects."""

    ON_CONFLICT_DO_UPDATE = "on_conflict_do_update"
    ON_CONFLICT_DO_NOTHING = "on_conflict_do_nothing"
    INSERT_OR_REPLACE = "insert_or_replace"
    INSERT_OR_IGNORE = "insert_or_ignore"


def upsert_clause(
    style: UpsertStyle,
    conflict_target: tuple[str, ...] | None = None,
    update_columns: tuple[str, ...] | None = None,
    update_expressions: Mapping[str, str] | None = None,
) -> str:
    """Build the dialect-neutral ``ON CONFLICT`` suffix for an upsert."""
    conflict = f" ({', '.join(conflict_target)})" if conflict_target else ""
    if style is UpsertStyle.ON_CONFLICT_DO_UPDATE:
        expressions = update_expressions or {}
        if not update_columns:
            raise ValueError("ON_CONFLICT_DO_UPDATE requires at least one update column")
        update_set = ", ".join(
            f"{column} = {expressions.get(column, f'excluded.{column}')}"
            for column in (update_columns or ())
        )
        return f" ON CONFLICT{conflict} DO UPDATE SET {update_set}"
    if style is UpsertStyle.ON_CONFLICT_DO_NOTHING:
        return f" ON CONFLICT{conflict} DO NOTHING"
    return ""


class SqlDialect:
    """Render SQL for SQLite without changing existing question-mark binds."""

    placeholder: PlaceholderGenerator = QUESTION_MARK

    def translate(self, sql: str) -> str:
        """Return SQLite SQL unchanged."""
        return sql

    @staticmethod
    def render_upsert(
        style: UpsertStyle,
        columns: tuple[str, ...],
        conflict_target: tuple[str, ...] | None = None,
        update_columns: tuple[str, ...] | None = None,
        update_expressions: Mapping[str, str] | None = None,
    ) -> str:
        """Render an SQLite upsert suffix for the requested style."""
        if update_columns is None:
            update_columns = tuple(
                column for column in columns if column not in (conflict_target or ())
            )
        suffix = upsert_clause(style, conflict_target, update_columns, update_expressions)
        if suffix:
            return suffix
        if style is UpsertStyle.INSERT_OR_REPLACE:
            return " OR REPLACE"
        if style is UpsertStyle.INSERT_OR_IGNORE:
            return " OR IGNORE"
        return ""


class PgDialect:
    """Render SQLite-shaped SQL with PostgreSQL numbered bind parameters."""

    placeholder: PlaceholderGenerator = DOLLAR

    def translate(self, sql: str) -> str:
        """Translate question-mark binds while preserving quoted literals."""
        return translate_question_marks(sql, target="dollar")

    @staticmethod
    def render_upsert(
        style: UpsertStyle,
        columns: tuple[str, ...],
        conflict_target: tuple[str, ...] | None = None,
        update_columns: tuple[str, ...] | None = None,
        update_expressions: Mapping[str, str] | None = None,
    ) -> str:
        """Render a PostgreSQL-compatible upsert suffix or fail explicitly."""
        if update_columns is None:
            update_columns = tuple(
                column for column in columns if column not in (conflict_target or ())
            )
        suffix = upsert_clause(style, conflict_target, update_columns, update_expressions)
        if suffix:
            return suffix
        raise NotImplementedError(
            f"PgDialect.render_upsert: {style.value!r} not supported; "
            "use ON_CONFLICT_DO_UPDATE or ON_CONFLICT_DO_NOTHING"
        )


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

    def _upsert_sql(
        self,
        *,
        table: str,
        columns: tuple[str, ...],
        style: UpsertStyle,
        conflict_target: tuple[str, ...] | None = None,
        update_columns: tuple[str, ...] | None = None,
        update_expressions: Mapping[str, str] | None = None,
    ) -> str:
        """Build an INSERT statement with a dialect-specific upsert suffix."""
        placeholders = ", ".join("?" for _ in columns)
        col_list = ", ".join(columns)
        if update_columns is None:
            update_columns = tuple(
                column for column in columns if column not in (conflict_target or ())
            )
        suffix = self._dialect.render_upsert(
            style,
            columns=columns,
            conflict_target=conflict_target,
            update_columns=update_columns,
            update_expressions=update_expressions,
        )
        statement = (
            f"INSERT INTO {table} ({col_list}) "  # noqa: S608 - repository-owned identifiers
            f"VALUES ({placeholders}){suffix}"
        )
        return statement


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
