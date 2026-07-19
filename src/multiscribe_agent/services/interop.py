"""API key issuance, approval, and verification for external AI access."""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Literal

from multiscribe_agent.domain.models import InteropKey
from multiscribe_agent.infra.db import Database

Mode = Literal["whitelist", "approval"]


@dataclass(frozen=True, slots=True)
class IssuedKey:
    """Plaintext credential returned only at registration time."""

    api_key: str
    key_id: str


class InteropError(RuntimeError):
    """Raised for interop authentication and authorization failures."""


class InteropService:
    """Persist and verify external AI keys against the application database."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def generate_key(self, description: str, mode: Mode = "whitelist") -> IssuedKey:
        """Create a random key and persist only its SHA-256 digest."""
        secret = "sk_" + secrets.token_urlsafe(32)
        key_id = "ik_" + secrets.token_urlsafe(8)
        record = InteropKey(
            key_id=key_id,
            key_hash=hash_api_key(secret),
            description=description.strip()[:200],
            created_at=int(time.time()),
            approved=mode == "whitelist",
        )
        await self._database.execute(
            "INSERT INTO interop_keys "
            "(key_id, key_hash, description, created_at, approved, rate_limit_per_minute) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                record.key_id,
                record.key_hash,
                record.description,
                record.created_at,
                int(record.approved),
                record.rate_limit_per_minute,
            ),
        )
        return IssuedKey(api_key=secret, key_id=key_id)

    async def verify_key(self, api_key: str) -> InteropKey:
        """Look up a key by hash and reject missing or pending credentials."""
        if not api_key.startswith("sk_"):
            raise InteropError("api_key must start with sk_")
        row = await self._database.fetchone(
            "SELECT key_id, key_hash, description, created_at, approved, "
            "rate_limit_per_minute, last_used_at, request_count "
            "FROM interop_keys WHERE key_hash = ?",
            (hash_api_key(api_key),),
        )
        if row is None:
            raise InteropError("invalid api_key")
        record = InteropKey(
            key_id=str(row["key_id"]),
            key_hash=str(row["key_hash"]),
            description=str(row["description"]),
            created_at=int(row["created_at"]),
            approved=bool(row["approved"]),
            rate_limit_per_minute=int(row["rate_limit_per_minute"]),
            last_used_at=int(row["last_used_at"]) if row["last_used_at"] is not None else None,
            request_count=int(row["request_count"]),
        )
        if not record.approved:
            raise InteropError("api_key not yet approved")
        return record

    async def approve_key(self, key_id: str) -> bool:
        """Mark a pending key as approved."""
        return (
            await self._database.execute(
                "UPDATE interop_keys SET approved = 1 WHERE key_id = ?", (key_id,)
            )
            > 0
        )

    async def touch_usage(self, key_id: str) -> None:
        """Increment usage counters after a successful authentication check."""
        await self._database.execute(
            "UPDATE interop_keys SET request_count = request_count + 1, last_used_at = ? "
            "WHERE key_id = ?",
            (int(time.time()), key_id),
        )


def hash_api_key(api_key: str) -> str:
    """Return the stable SHA-256 representation used in storage."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()
