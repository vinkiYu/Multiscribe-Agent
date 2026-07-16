"""SQLite repository for hashed API key metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import aiosqlite

from multiscribe_agent.infra.db import Database


class ApiKeyRepository:
    """Persist API key hashes and lifecycle metadata without plaintext secrets."""

    def __init__(self, db: Database) -> None:
        """Create a repository using an initialized database."""
        self._db = db

    async def create(
        self,
        key_id: str,
        name: str,
        key_hash: str,
        prefix: str,
        source_fingerprint: str,
        verification_token: str,
        status: str,
    ) -> None:
        """Insert one API key record with the current creation timestamp."""
        await self._db.execute(
            """
            INSERT INTO api_keys(
                id, name, key_hash, prefix, source_fingerprint, verification_token,
                status, created_at, last_used_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                key_id,
                name,
                key_hash,
                prefix,
                source_fingerprint,
                verification_token,
                status,
                self._now(),
            ),
        )

    async def get_by_prefix(self, prefix: str) -> dict[str, Any] | None:
        """Return one API key record by its public prefix."""
        row = await self._db.fetchone("SELECT * FROM api_keys WHERE prefix = ?", (prefix,))
        return None if row is None else self._to_dict(row)

    async def get_by_token(self, token: str) -> dict[str, Any] | None:
        """Return one API key record by its verification token."""
        row = await self._db.fetchone(
            "SELECT * FROM api_keys WHERE verification_token = ?",
            (token,),
        )
        return None if row is None else self._to_dict(row)

    async def update_status(self, key_id: str, status: str) -> None:
        """Change the status of an API key record."""
        await self._db.execute("UPDATE api_keys SET status = ? WHERE id = ?", (status, key_id))

    async def update_last_used(self, key_id: str) -> None:
        """Record the current UTC timestamp as the key's last use."""
        await self._db.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
            (self._now(), key_id),
        )

    async def list_all(self) -> list[dict[str, Any]]:
        """Return all API key records ordered by creation time."""
        rows = await self._db.fetchall("SELECT * FROM api_keys ORDER BY created_at DESC")
        return [self._to_dict(row) for row in rows]

    @staticmethod
    def _now() -> str:
        """Return an ISO-8601 UTC timestamp."""
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _to_dict(row: aiosqlite.Row) -> dict[str, Any]:
        """Convert a SQLite row to a dynamic API key metadata mapping."""
        return cast(dict[str, Any], dict(row))
