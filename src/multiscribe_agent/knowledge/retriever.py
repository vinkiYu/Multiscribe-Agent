"""FTS5 and optional vector reciprocal-rank-fusion retrieval."""

from __future__ import annotations

from dataclasses import dataclass

from multiscribe_agent.infra.db import Database
from multiscribe_agent.knowledge.embedding_service import EmbeddingService
from multiscribe_agent.knowledge.vector_store import VectorStore, VectorStoreUnavailable


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    """One content chunk ranked by one or both knowledge retrieval methods."""

    chunk_id: str
    document_id: str
    content: str
    score: float
    source: list[str]


class Retriever:
    """Fuse FTS5 and vector ranking with the standard reciprocal-rank formula."""

    RRF_K = 60

    def __init__(
        self,
        db: Database,
        vector_store: VectorStore | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self._db = db
        self._vector_store = vector_store
        self._embedding_service = embedding_service

    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        candidate_k: int = 20,
        vector_weight: float = 1.0,
        fts_weight: float = 1.0,
    ) -> list[RetrievalHit]:
        """Retrieve FTS candidates, optionally add vector candidates, then RRF-fuse."""
        fts_ids = await self._fts_chunk_ids(query, candidate_k)
        vector_ids: list[str] = []
        if self._vector_store is not None and self._embedding_service is not None:
            try:
                vector = await self._embedding_service.encode_one(query)
                vector_ids = [
                    chunk_id for chunk_id, _ in await self._vector_store.top_k(vector, candidate_k)
                ]
            except VectorStoreUnavailable:
                vector_ids = []
        scores: dict[str, float] = {}
        sources: dict[str, list[str]] = {}
        _add_rrf(scores, sources, fts_ids, "fts", fts_weight)
        _add_rrf(scores, sources, vector_ids, "vector", vector_weight)
        if not scores:
            return []
        ordered = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)[:top_k]
        placeholders = ",".join("?" for _ in ordered)
        statement = f"SELECT id, document_id, content FROM kb_chunks WHERE id IN ({placeholders})"  # noqa: S608
        rows = await self._db.fetchall(
            statement,
            ordered,
        )
        row_by_id = {str(row["id"]): row for row in rows}
        return [
            RetrievalHit(
                chunk_id=chunk_id,
                document_id=str(row_by_id[chunk_id]["document_id"]),
                content=str(row_by_id[chunk_id]["content"]),
                score=scores[chunk_id],
                source=sources[chunk_id],
            )
            for chunk_id in ordered
            if chunk_id in row_by_id
        ]

    async def _fts_chunk_ids(self, query: str, candidate_k: int) -> list[str]:
        """Return FTS5 chunk IDs without exposing query grammar to callers."""
        terms = " ".join(part for part in query.replace("'", " ").split() if part)
        if not terms:
            return []
        try:
            rows = await self._db.fetchall(
                """
                SELECT kb_chunks.id
                FROM kb_chunks_fts
                JOIN kb_chunks ON kb_chunks.rowid = kb_chunks_fts.rowid
                WHERE kb_chunks_fts MATCH ?
                ORDER BY bm25(kb_chunks_fts)
                LIMIT ?
                """,
                (terms, candidate_k),
            )
        except Exception:
            return []
        return [str(row["id"]) for row in rows]


def _add_rrf(
    scores: dict[str, float],
    sources: dict[str, list[str]],
    ids: list[str],
    source: str,
    weight: float,
) -> None:
    """Accumulate one ranked candidate list into RRF score and provenance maps."""
    for rank, chunk_id in enumerate(ids, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (Retriever.RRF_K + rank)
        sources.setdefault(chunk_id, []).append(source)
