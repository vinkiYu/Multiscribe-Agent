"""PostgreSQL pgvector persistence adapter for knowledge chunks."""

from __future__ import annotations

import json
from collections.abc import Sequence

from multiscribe_agent.infra.db_protocol import DatabaseProtocol


class PostgresVectorStore:
    """Store and retrieve embeddings using pgvector cosine distance."""

    __slots__ = ("_db", "_dim")

    def __init__(self, db: DatabaseProtocol, dim: int = 384) -> None:
        """Create a vector store over a PostgreSQL-compatible database port."""
        if dim <= 0:
            raise ValueError("embedding dimension must be positive")
        self._db = db
        self._dim = dim

    async def upsert(self, chunk_id: str, embedding: Sequence[float]) -> None:
        """Store one exact-dimension vector using a PostgreSQL upsert."""
        _validate_dimension(embedding, self._dim, "embedding")
        encoded = json.dumps(list(embedding), separators=(",", ":"))
        await self._db.execute(
            """
            INSERT INTO chunk_vectors(chunk_id, embedding)
            VALUES ($1, $2::vector)
            ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding
            """,
            (chunk_id, encoded),
        )

    async def delete(self, chunk_id: str) -> None:
        """Remove one chunk vector."""
        await self._db.execute("DELETE FROM chunk_vectors WHERE chunk_id = $1", (chunk_id,))

    async def top_k(self, query: Sequence[float], k: int = 20) -> list[tuple[str, float]]:
        """Return nearest vectors ordered by ascending cosine distance."""
        _validate_dimension(query, self._dim, "query")
        if k <= 0:
            return []
        encoded = json.dumps(list(query), separators=(",", ":"))
        rows = await self._db.fetchall(
            """
            SELECT chunk_id, embedding <=> $1::vector AS distance
            FROM chunk_vectors
            ORDER BY embedding <=> $2::vector
            LIMIT $3
            """,
            (encoded, encoded, k),
        )
        return [(str(row["chunk_id"]), float(row["distance"])) for row in rows]


def _validate_dimension(values: Sequence[float], dimension: int, name: str) -> None:
    """Reject vectors whose shape cannot be stored in the pgvector column."""
    if len(values) != dimension:
        raise ValueError(f"{name} must contain {dimension} dimensions")
