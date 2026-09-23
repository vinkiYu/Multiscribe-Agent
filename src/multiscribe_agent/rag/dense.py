"""Vector retrieval adapter for the P66 backend-neutral VectorStorePort."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import structlog

from multiscribe_agent.domain.ports import VectorStorePort
from multiscribe_agent.infra.db_protocol import DatabaseProtocol
from multiscribe_agent.infra.dialect import DialectRepositoryMixin
from multiscribe_agent.knowledge.embedding_service import EmbeddingUnavailableError
from multiscribe_agent.knowledge.vector_store import VectorStoreUnavailable
from multiscribe_agent.rag.models import RetrievalScope
from multiscribe_agent.rag.schema import scope_predicate

log = structlog.get_logger(__name__)


class QueryEmbedder(Protocol):
    """Minimal query encoder accepted by the dense retriever."""

    async def encode_one(self, text: str) -> list[float]:
        """Encode one query into the configured embedding space."""
        ...


@dataclass(frozen=True, slots=True)
class DenseHit:
    """One scope-valid vector candidate."""

    chunk_id: str
    distance: float


class RagDenseRetriever(DialectRepositoryMixin):
    """Encode a query, ask the vector port for candidates, then enforce scope in SQL."""

    _db: DatabaseProtocol

    def __init__(
        self,
        db: DatabaseProtocol,
        vector_store: VectorStorePort | None,
        embedding_service: QueryEmbedder | None,
    ) -> None:
        """Bind optional vector dependencies without importing a concrete backend."""
        self._db = db
        self._vector_store = vector_store
        self._embedding_service = embedding_service
        self.available = vector_store is not None and embedding_service is not None

    async def search(
        self,
        query: str,
        scope: RetrievalScope,
        *,
        candidate_k: int = 20,
    ) -> list[DenseHit]:
        """Return vector candidates whose registry rows satisfy the scope."""
        if not query.strip() or candidate_k < 1 or not self.available:
            return []
        vector_store = self._vector_store
        embedding_service = self._embedding_service
        if vector_store is None or embedding_service is None:
            return []
        try:
            vector = await embedding_service.encode_one(query)
            vector_hits = await vector_store.top_k(vector, candidate_k)
        except (EmbeddingUnavailableError, VectorStoreUnavailable, RuntimeError, ValueError) as exc:
            self.available = False
            log.warning("rag_vector_unavailable", error=type(exc).__name__)
            return []
        if not vector_hits:
            return []

        ordered_ids = [str(chunk_id) for chunk_id, _distance in vector_hits]
        placeholders = ", ".join("?" for _ in ordered_ids)
        predicate, scope_parameters = scope_predicate(scope)
        statement = (
            "SELECT rc.chunk_id FROM rag_chunks rc "  # noqa: S608
            "JOIN rag_index_registry rir ON rir.chunk_id = rc.chunk_id "
            f"WHERE rc.chunk_id IN ({placeholders}) AND {predicate}"
        )
        try:
            rows = await self._fetchall(statement, [*ordered_ids, *scope_parameters])
        except Exception as exc:  # Backend-specific missing-index errors vary by driver.
            log.warning("rag_vector_scope_filter_unavailable", error=type(exc).__name__)
            return []
        valid = {str(row["chunk_id"]) for row in rows}
        distance_by_id = {str(chunk_id): float(distance) for chunk_id, distance in vector_hits}
        return [
            DenseHit(chunk_id=chunk_id, distance=distance_by_id[chunk_id])
            for chunk_id in ordered_ids
            if chunk_id in valid
        ]


__all__ = ["DenseHit", "QueryEmbedder", "RagDenseRetriever"]
