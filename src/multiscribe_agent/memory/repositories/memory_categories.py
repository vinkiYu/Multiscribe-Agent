"""Dedicated CRUD access to durable memory categories."""

from __future__ import annotations

import json

from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.dialect import DialectRepositoryMixin, PgDialect


class MemoryCategoryRepository(DialectRepositoryMixin):
    """Read and write JSON category records without using the generic entity store."""

    def __init__(self, db: Database) -> None:
        """Bind this repository to an initialized SQLite database."""
        self._db = db

    async def get(self, category_id: str) -> dict[str, object] | None:
        """Return one category data object when it exists."""
        row = await self._fetchone(
            "SELECT data FROM memory_categories WHERE id = ?", (category_id,)
        )
        if row is None:
            return None
        value = json.loads(str(row["data"]))
        if not isinstance(value, dict):
            raise ValueError("memory category data must be an object")
        return {str(key): item for key, item in value.items()}

    async def save(self, category_id: str, data: dict[str, object]) -> None:
        """Create or replace one category record."""
        statement = (
            "INSERT INTO memory_categories(id, data) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = EXCLUDED.data"
            if isinstance(self._dialect, PgDialect)
            else "INSERT OR REPLACE INTO memory_categories(id, data) VALUES (?, ?)"
        )
        await self._execute(
            statement,
            (category_id, json.dumps(data, ensure_ascii=False, sort_keys=True)),
        )

    async def list_all(self) -> list[dict[str, object]]:
        """Return all category data objects with their stable identifiers."""
        rows = await self._fetchall("SELECT id, data FROM memory_categories ORDER BY id")
        values: list[dict[str, object]] = []
        for row in rows:
            data = json.loads(str(row["data"]))
            if not isinstance(data, dict):
                raise ValueError("memory category data must be an object")
            values.append({"id": str(row["id"]), **{str(key): item for key, item in data.items()}})
        return values

    async def delete(self, category_id: str) -> bool:
        """Delete one category and report whether a record was removed."""
        result = await self._execute("DELETE FROM memory_categories WHERE id = ?", (category_id,))
        return (result or 0) > 0
