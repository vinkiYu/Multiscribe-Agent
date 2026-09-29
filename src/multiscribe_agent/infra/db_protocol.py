"""PostgreSQL database contract and repository SQL helpers.

P67 intentionally removes the previous SQLite/PostgreSQL dialect abstraction.
Repositories still use the small helper mixin so SQL construction remains
centralised, but the only supported runtime is PostgreSQL and every statement
is normalised to PostgreSQL's ``$n`` bind syntax before execution.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from multiscribe_agent.infra.placeholder import translate_question_marks

SqlParameters = tuple[Any, ...] | list[Any]


@runtime_checkable
class DatabaseProtocol(Protocol):
    """The application-facing subset of an ``asyncpg`` connection pool."""

    async def execute(self, statement: str, parameters: SqlParameters = ()) -> int | None:
        """Execute one statement and return its count or scalar RETURNING value."""

    async def executemany(self, statement: str, parameters: Sequence[SqlParameters]) -> int:
        """Execute one statement for a batch of parameter sets."""

    async def fetchone(
        self, statement: str, parameters: SqlParameters = ()
    ) -> Mapping[str, Any] | None:
        """Return the first result row as a string-keyed mapping."""

    async def fetchall(
        self, statement: str, parameters: SqlParameters = ()
    ) -> list[Mapping[str, Any]]:
        """Return all result rows as string-keyed mappings."""

    async def close(self) -> None:
        """Close the backend connection or pool."""

    def set_audit_logger(self, audit_logger: object | None) -> None:
        """Attach an optional write-audit sink."""


class PostgresRepositoryMixin:
    """One-way repository helpers for the PostgreSQL-only persistence layer."""

    _db: DatabaseProtocol

    @staticmethod
    def _sql(statement: str) -> str:
        """Translate legacy question-mark binds to PostgreSQL ``$n`` binds.

        The conversion is deliberately one-way and lives at the repository
        boundary only; no runtime dialect selection remains after P67.
        """
        return translate_question_marks(statement, target="dollar")

    async def _execute(
        self, statement: str, parameters: tuple[Any, ...] | list[Any] = ()
    ) -> int | None:
        """Execute one PostgreSQL statement."""
        return await self._db.execute(self._sql(statement), parameters)

    async def _executemany(self, statement: str, parameters: Sequence[SqlParameters]) -> int:
        """Execute a PostgreSQL statement for a batch of rows."""
        return await self._db.executemany(self._sql(statement), parameters)

    async def _fetchone(
        self, statement: str, parameters: tuple[Any, ...] | list[Any] = ()
    ) -> Mapping[str, Any] | None:
        """Fetch one PostgreSQL row."""
        return await self._db.fetchone(self._sql(statement), parameters)

    async def _fetchall(
        self, statement: str, parameters: tuple[Any, ...] | list[Any] = ()
    ) -> list[Mapping[str, Any]]:
        """Fetch all PostgreSQL rows."""
        return await self._db.fetchall(self._sql(statement), parameters)

    @staticmethod
    def _json_extract(column: str, path: str) -> str:
        """Render a trusted JSONB scalar extraction expression."""
        if not column.replace("_", "").isalnum() or not path.replace("_", "").isalnum():
            raise ValueError("JSON extraction identifiers must be trusted names")
        return f"{column}->>'{path}'"

    @staticmethod
    def _upsert_sql(
        *,
        table: str,
        columns: tuple[str, ...],
        conflict_target: tuple[str, ...],
        update_columns: tuple[str, ...] | None = None,
        update_expressions: Mapping[str, str] | None = None,
    ) -> str:
        """Build one PostgreSQL ``ON CONFLICT`` upsert statement."""
        if update_columns is None:
            update_columns = tuple(column for column in columns if column not in conflict_target)
        if not update_columns:
            raise ValueError("PostgreSQL upsert requires update columns")
        values = ", ".join(f"${index}" for index in range(1, len(columns) + 1))
        updates = ", ".join(
            f"{column} = {(update_expressions or {}).get(column, f'EXCLUDED.{column}')}"
            for column in update_columns
        )
        return (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({values}) "  # noqa: S608 - identifiers are trusted constants.
            f"ON CONFLICT ({', '.join(conflict_target)}) DO UPDATE SET {updates}"
        )


class ExplicitPostgresRepositoryMixin:
    """One-way helper for services that receive the database per call."""

    @staticmethod
    def _sql(statement: str) -> str:
        """Translate legacy question-mark binds to PostgreSQL binds."""
        return translate_question_marks(statement, target="dollar")

    async def _execute(
        self,
        db: DatabaseProtocol,
        statement: str,
        parameters: tuple[Any, ...] | list[Any] = (),
    ) -> int | None:
        """Execute one PostgreSQL statement."""
        return await db.execute(self._sql(statement), parameters)

    async def _fetchone(
        self,
        db: DatabaseProtocol,
        statement: str,
        parameters: tuple[Any, ...] | list[Any] = (),
    ) -> Mapping[str, Any] | None:
        """Fetch one PostgreSQL row."""
        return await db.fetchone(self._sql(statement), parameters)

    async def _fetchall(
        self,
        db: DatabaseProtocol,
        statement: str,
        parameters: tuple[Any, ...] | list[Any] = (),
    ) -> list[Mapping[str, Any]]:
        """Fetch all PostgreSQL rows."""
        return await db.fetchall(self._sql(statement), parameters)
