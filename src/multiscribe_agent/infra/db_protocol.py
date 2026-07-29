"""Backend-neutral database contract used by persistence boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

SqlParameters = tuple[Any, ...] | list[Any]


@runtime_checkable
class DatabaseProtocol(Protocol):
    """Backend-agnostic database surface for repositories and services."""

    async def execute(self, statement: str, parameters: SqlParameters = ()) -> int:
        """Execute one statement and return the affected row count."""

    async def executemany(self, statement: str, parameters: list[SqlParameters]) -> int:
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
