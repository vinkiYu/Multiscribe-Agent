"""Idempotent ownership migrations for the P66 derived RAG indexes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from multiscribe_agent.infra.db_protocol import DatabaseProtocol
from multiscribe_agent.infra.dialect import DialectRepositoryMixin
from multiscribe_agent.rag.schema import RagChunksStore

OWNER_MIGRATION_ID = "p66.4-rag-owner-admin-v1"


@dataclass(frozen=True, slots=True)
class RagOwnerMigrationReport:
    """Counts and marker state produced by the ownership backfill."""

    registry_updated: int = 0
    chunks_updated: int = 0
    already_marked: bool = False


class RagOwnerMigration(DialectRepositoryMixin):
    """Backfill the legacy ``default`` owner without changing source facts."""

    _db: DatabaseProtocol

    def __init__(self, db: DatabaseProtocol) -> None:
        """Bind the backend-neutral database contract."""
        self._db = db

    async def apply(
        self,
        *,
        owner_user_id: str = "admin",
        legacy_user_id: str = "default",
    ) -> RagOwnerMigrationReport:
        """Ensure the derived RAG tables exist and idempotently rewrite legacy owners."""
        owner = owner_user_id.strip()
        legacy = legacy_user_id.strip()
        if not owner or not legacy:
            raise ValueError("owner user IDs must not be empty")

        await RagChunksStore(self._db).ensure_schema()
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS rag_migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        marker = await self._fetchone(
            "SELECT migration_id FROM rag_migrations WHERE migration_id = ?",
            (OWNER_MIGRATION_ID,),
        )
        registry_updated = int(
            await self._execute(
                "UPDATE rag_index_registry SET user_id = ? WHERE user_id = ?",
                (owner, legacy),
            )
            or 0
        )
        chunks_updated = int(
            await self._execute(
                "UPDATE rag_chunks SET user_id = ? WHERE user_id = ?",
                (owner, legacy),
            )
            or 0
        )
        if marker is None:
            await self._execute(
                "INSERT INTO rag_migrations(migration_id, applied_at) VALUES (?, ?)",
                (OWNER_MIGRATION_ID, datetime.now(UTC).isoformat()),
            )
        return RagOwnerMigrationReport(
            registry_updated=registry_updated,
            chunks_updated=chunks_updated,
            already_marked=marker is not None,
        )


async def migrate_rag_owner(
    db: DatabaseProtocol,
    *,
    owner_user_id: str = "admin",
    legacy_user_id: str = "default",
) -> RagOwnerMigrationReport:
    """Run the P66.4 ownership migration through the backend-neutral adapter."""
    return await RagOwnerMigration(db).apply(
        owner_user_id=owner_user_id,
        legacy_user_id=legacy_user_id,
    )


__all__ = [
    "OWNER_MIGRATION_ID",
    "RagOwnerMigration",
    "RagOwnerMigrationReport",
    "migrate_rag_owner",
]
