"""PostgreSQL/pgvector persistence adapter for RAG chunk embeddings."""

from __future__ import annotations

from collections.abc import Sequence

from multiscribe_agent.infra.db_protocol import DatabaseProtocol, PostgresRepositoryMixin


class VectorStoreUnavailable(RuntimeError):
    """Raised when pgvector cannot execute a vector operation."""


class VectorStore(PostgresRepositoryMixin):
    """Persist and retrieve fixed-dimension vectors in ``chunk_vectors``."""

    def __init__(self, db: DatabaseProtocol, dim: int = 512) -> None:
        """Bind the PostgreSQL database and expected embedding dimension."""
        if dim <= 0:
            raise ValueError("vector dimension must be positive")
        self._db = db
        self._dim = dim

    async def upsert(self, chunk_id: str, embedding: Sequence[float]) -> None:
        """Store one exact-dimension vector using pgvector's native array cast."""
        if len(embedding) != self._dim:
            raise ValueError(f"embedding must contain {self._dim} dimensions")
        await self._execute(
            "INSERT INTO chunk_vectors(chunk_id, embedding) VALUES (?, ?::vector) "
            "ON CONFLICT(chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding",
            (chunk_id, _vector_literal(embedding)),
        )

    async def delete(self, chunk_id: str) -> None:
        """Remove one chunk vector."""
        await self._execute("DELETE FROM chunk_vectors WHERE chunk_id = ?", (chunk_id,))

    async def top_k(self, query: Sequence[float], k: int = 20) -> list[tuple[str, float]]:
        """Return nearest vectors ordered by cosine distance."""
        if len(query) != self._dim:
            raise ValueError(f"query must contain {self._dim} dimensions")
        if k < 1:
            return []
        try:
            literal = _vector_literal(query)
            rows = await self._fetchall(
                "SELECT chunk_id, embedding <=> ?::vector AS distance "
                "FROM chunk_vectors ORDER BY embedding <=> ?::vector LIMIT ?",
                (literal, literal, k),
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            raise VectorStoreUnavailable("pgvector search is unavailable") from exc
        return [(str(row["chunk_id"]), float(row["distance"])) for row in rows]


def _vector_literal(values: Sequence[float]) -> str:
    """Render a pgvector text literal without relying on driver codecs."""
    return "[" + ",".join(format(float(value), ".9g") for value in values) + "]"


__all__ = ["VectorStore", "VectorStoreUnavailable"]
