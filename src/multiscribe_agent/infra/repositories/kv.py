"""SQLite-backed key-value repository with JSON serialization and TTL support."""

from __future__ import annotations

import json
import time
from typing import cast

from multiscribe_agent.infra.db import Database


class KvRepository:
    """Persist JSON-compatible values by key in SQLite."""

    def __init__(self, db: Database) -> None:
        """Create a repository using an initialized database."""
        self._db = db

    async def get(self, key: str) -> object | None:
        """Return a value or delete it first when its TTL has elapsed."""
        row = await self._db.fetchone(
            "SELECT value, expires_at FROM kv WHERE key = ?",
            (key,),
        )
        if row is None:
            return None

        expires_at = row["expires_at"]
        if expires_at is not None and float(expires_at) <= time.time():
            await self.delete(key)
            return None

        value = str(row["value"])
        try:
            return cast(object, json.loads(value))
        except json.JSONDecodeError:
            return value

    async def set(self, key: str, value: object, ttl_seconds: int | None = None) -> None:
        """Serialize a value and upsert it with an optional expiration timestamp."""
        expires_at = None if ttl_seconds is None else time.time() + ttl_seconds
        await self._db.execute(
            """
            INSERT INTO kv(key, value, expires_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, expires_at = excluded.expires_at
            """,
            (key, json.dumps(value), expires_at),
        )

    async def delete(self, key: str) -> None:
        """Delete a key if it exists."""
        await self._db.execute("DELETE FROM kv WHERE key = ?", (key,))
