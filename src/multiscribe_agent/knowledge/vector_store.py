"""Optional sqlite-vec persistence adapter."""

from __future__ import annotations

import struct
from collections.abc import Sequence

from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.dialect import DialectRepositoryMixin, PgDialect


class VectorStoreUnavailable(RuntimeError):
    """Raised when sqlite-vec cannot be used by the active SQLite connection."""


class VectorStore(DialectRepositoryMixin):
    """Persist and retrieve chunk vectors from an initialized vec0 table."""

    def __init__(self, db: Database, dim: int = 384) -> None:
        self._db = db
        self._dim = dim

    async def upsert(self, chunk_id: str, embedding: Sequence[float]) -> None:
        """Store one exact-dimension float32 vector."""
        if len(embedding) != self._dim:
            raise ValueError(f"embedding must contain {self._dim} dimensions")
        if isinstance(self._dialect, PgDialect):
            await self._execute(
                "INSERT INTO chunk_vectors(chunk_id, embedding) VALUES (?, ?) "
                "ON CONFLICT(chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding",
                (chunk_id, list(embedding)),
            )
        else:
            await self._execute(
                "INSERT OR REPLACE INTO kb_chunks_vec(chunk_id, embedding) VALUES (?, ?)",
                (chunk_id, struct.pack(f"<{self._dim}f", *embedding)),
            )

    async def delete(self, chunk_id: str) -> None:
        """Remove one chunk vector."""
        table = "chunk_vectors" if isinstance(self._dialect, PgDialect) else "kb_chunks_vec"
        await self._execute(f"DELETE FROM {table} WHERE chunk_id = ?", (chunk_id,))  # noqa: S608

    async def top_k(self, query: Sequence[float], k: int = 20) -> list[tuple[str, float]]:
        """Return nearest vectors in ascending sqlite-vec distance order."""
        if len(query) != self._dim:
            raise ValueError(f"query must contain {self._dim} dimensions")
        try:
            if isinstance(self._dialect, PgDialect):
                rows = await self._fetchall(
                    "SELECT chunk_id, embedding <=> ? AS distance FROM chunk_vectors "
                    "ORDER BY embedding <=> ? LIMIT ?",
                    (list(query), list(query), k),
                )
            else:
                rows = await self._fetchall(
                    "SELECT chunk_id, distance FROM kb_chunks_vec "
                    "WHERE embedding MATCH ? AND k = ?",
                    (struct.pack(f"<{self._dim}f", *query), k),
                )
        except Exception as exc:
            raise VectorStoreUnavailable("sqlite-vec search is unavailable") from exc
        return [(str(row["chunk_id"]), float(row["distance"])) for row in rows]
