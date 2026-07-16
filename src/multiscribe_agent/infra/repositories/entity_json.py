"""Whitelisted JSON blob repository for declarative entities."""

from __future__ import annotations

import json
from typing import Any, cast

from multiscribe_agent.infra.db import Database

_TABLE_STATEMENTS = {
    "agents": (
        "SELECT data FROM agents WHERE id = ?",
        "INSERT OR REPLACE INTO agents(id, data) VALUES (?, ?)",
        "SELECT data FROM agents ORDER BY id",
        "DELETE FROM agents WHERE id = ?",
    ),
    "skills": (
        "SELECT data FROM skills WHERE id = ?",
        "INSERT OR REPLACE INTO skills(id, data) VALUES (?, ?)",
        "SELECT data FROM skills ORDER BY id",
        "DELETE FROM skills WHERE id = ?",
    ),
    "workflows": (
        "SELECT data FROM workflows WHERE id = ?",
        "INSERT OR REPLACE INTO workflows(id, data) VALUES (?, ?)",
        "SELECT data FROM workflows ORDER BY id",
        "DELETE FROM workflows WHERE id = ?",
    ),
    "mcp_configs": (
        "SELECT data FROM mcp_configs WHERE id = ?",
        "INSERT OR REPLACE INTO mcp_configs(id, data) VALUES (?, ?)",
        "SELECT data FROM mcp_configs ORDER BY id",
        "DELETE FROM mcp_configs WHERE id = ?",
    ),
    "schedules": (
        "SELECT data FROM schedules WHERE id = ?",
        """
        INSERT OR REPLACE INTO schedules(id, data, updated_at)
        VALUES (?, ?, datetime('now'))
        """,
        "SELECT data FROM schedules ORDER BY id",
        "DELETE FROM schedules WHERE id = ?",
    ),
}


class EntityJsonRepository:
    """Store JSON documents in a fixed set of entity tables."""

    def __init__(self, db: Database) -> None:
        """Create a repository using an initialized database."""
        self._db = db

    async def get(self, table: str, entity_id: str) -> dict[str, Any] | None:
        """Return one JSON entity by table and identifier."""
        statements = self._statements_for(table)
        row = await self._db.fetchone(
            statements[0],
            (entity_id,),
        )
        if row is None:
            return None
        return self._decode_object(str(row["data"]))

    async def save(self, table: str, entity_id: str, data: dict[str, Any]) -> None:
        """Insert or replace a JSON entity in an allowed table."""
        statements = self._statements_for(table)
        await self._db.execute(
            statements[1],
            (entity_id, json.dumps(data)),
        )

    async def list_all(self, table: str) -> list[dict[str, Any]]:
        """Return all JSON entities from an allowed table."""
        statements = self._statements_for(table)
        rows = await self._db.fetchall(statements[2])
        return [self._decode_object(str(row["data"])) for row in rows]

    async def delete(self, table: str, entity_id: str) -> None:
        """Delete an entity from an allowed table."""
        statements = self._statements_for(table)
        await self._db.execute(statements[3], (entity_id,))

    @staticmethod
    def _statements_for(table: str) -> tuple[str, str, str, str]:
        """Reject non-whitelisted table names before SQL construction."""
        statements = _TABLE_STATEMENTS.get(table)
        if statements is None:
            raise ValueError(f"unsupported entity table: {table}")
        return statements

    @staticmethod
    def _decode_object(raw_value: str) -> dict[str, Any]:
        """Decode a persisted JSON object and reject non-object values."""
        value = json.loads(raw_value)
        if not isinstance(value, dict):
            raise ValueError("stored entity data must be a JSON object")
        return cast(dict[str, Any], value)
