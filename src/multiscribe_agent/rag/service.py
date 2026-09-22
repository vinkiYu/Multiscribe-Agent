"""Hybrid BM25/vector retrieval service for the P66 RAG boundary."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

import structlog

from multiscribe_agent.domain.ports import VectorStorePort
from multiscribe_agent.infra.db_protocol import DatabaseProtocol
from multiscribe_agent.knowledge.embedding_service import EmbeddingService
from multiscribe_agent.rag.bm25 import Bm25Hit, RagBm25Retriever
from multiscribe_agent.rag.dense import DenseHit, QueryEmbedder, RagDenseRetriever
from multiscribe_agent.rag.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    RagCapabilities,
    RetrievalScope,
    RetrievedEvidence,
)
from multiscribe_agent.rag.ports import RagServiceProtocol
from multiscribe_agent.rag.schema import scope_predicate

log = structlog.get_logger(__name__)

IndexDocumentCallback = Callable[[KnowledgeDocument], Awaitable[int]]
RebuildIndexCallback = Callable[[list[str]], Awaitable[None]]


class RuntimeRagCapabilities(RagCapabilities):
    """Runtime capability view with the index-readiness state required by P66.3."""

    index_ready: bool = True

    @property
    def degraded(self) -> bool:
        """Treat a missing content index as a degraded retrieval state."""
        return super().degraded or not self.index_ready

    def as_dict(self) -> dict[str, bool]:
        """Expose backend-neutral flags, including index readiness."""
        values = super().as_dict()
        values["index_ready"] = self.index_ready
        return values


@dataclass(frozen=True, slots=True)
class _MergedHit:
    """RRF score and provenance accumulated for one chunk ID."""

    chunk_id: str
    score: float
    sources: tuple[str, ...]


class RagService(RagServiceProtocol):
    """Fuse P66-owned BM25 and vector retrieval into RetrievedEvidence."""

    RRF_K = 60

    def __init__(
        self,
        db: DatabaseProtocol,
        vector_store: VectorStorePort | None = None,
        embedding_service: QueryEmbedder | EmbeddingService | None = None,
        *,
        candidate_k: int = 20,
        vector_weight: float = 1.0,
        bm25_weight: float = 1.0,
        index_document_callback: IndexDocumentCallback | None = None,
        rebuild_index_callback: RebuildIndexCallback | None = None,
    ) -> None:
        """Create an independent service with explicitly injected dependencies."""
        if candidate_k < 1:
            raise ValueError("candidate_k must be positive")
        if vector_weight < 0 or bm25_weight < 0:
            raise ValueError("retrieval weights must be non-negative")
        self._db = db
        self._candidate_k = candidate_k
        self._vector_weight = vector_weight
        self._bm25_weight = bm25_weight
        self._bm25 = RagBm25Retriever(db)
        self._dense = RagDenseRetriever(db, vector_store, embedding_service)
        self._index_ready = True
        self._index_document_callback = index_document_callback
        self._rebuild_index_callback = rebuild_index_callback

    async def retrieve(
        self,
        query: str,
        scope: RetrievalScope,
        *,
        top_k: int = 10,
    ) -> list[RetrievedEvidence]:
        """Return scope-isolated evidence from hybrid RRF retrieval."""
        if top_k < 1 or not query.strip():
            return []
        candidate_k = max(self._candidate_k, top_k * 3)
        bm25_hits = await self._bm25.search(query, scope, candidate_k=candidate_k)
        self._index_ready = self._bm25.index_ready
        dense_hits = await self._dense.search(query, scope, candidate_k=candidate_k)
        merged = _merge_hits(bm25_hits, dense_hits, self._bm25_weight, self._vector_weight)
        if not merged:
            return []
        selected = merged[:top_k]
        rows = await self._fetch_rows([item.chunk_id for item in selected], scope)
        row_by_id = {str(row["chunk_id"]): row for row in rows}
        return [
            _to_evidence(item, row_by_id[item.chunk_id], scope)
            for item in selected
            if item.chunk_id in row_by_id
        ]

    async def index_document(self, doc: KnowledgeDocument) -> int:
        """Delegate indexing to the composition root's P66.2 adapter when supplied."""
        if self._index_document_callback is None:
            raise NotImplementedError(
                "RagService.index_document requires an injected indexing callback"
            )
        return await self._index_document_callback(doc)

    async def rebuild_index(self, doc_types: list[str]) -> None:
        """Delegate rebuild orchestration without coupling retrieval to adapters."""
        if self._rebuild_index_callback is None:
            raise NotImplementedError(
                "RagService.rebuild_index requires an injected indexing callback"
            )
        await self._rebuild_index_callback(doc_types)

    def capabilities(self) -> RagCapabilities:
        """Return current vector, embedding, FTS, and index-readiness flags."""
        vector_enabled = self._dense.available
        embedding_enabled = self._dense.available
        fts_enabled = self._index_ready
        return RuntimeRagCapabilities(
            vector_enabled=vector_enabled,
            embedding_enabled=embedding_enabled,
            fts_enabled=fts_enabled,
            index_ready=self._index_ready,
        )

    async def _fetch_rows(
        self, chunk_ids: list[str], scope: RetrievalScope
    ) -> list[dict[str, Any]]:
        """Fetch evidence metadata after applying the scope a second time."""
        placeholders = ", ".join("?" for _ in chunk_ids)
        predicate, parameters = scope_predicate(scope)
        statement = (
            "SELECT rc.*, rir.content_hash, rir.indexed_at "  # noqa: S608
            "FROM rag_chunks rc "
            "JOIN rag_index_registry rir ON rir.chunk_id = rc.chunk_id "
            f"WHERE rc.chunk_id IN ({placeholders}) AND {predicate}"
        )
        rows = await self._db.fetchall(self._translate(statement), [*chunk_ids, *parameters])
        return [dict(row) for row in rows]

    def _translate(self, statement: str) -> str:
        """Translate question-mark SQL through the active repository dialect."""
        from multiscribe_agent.infra.dialect import dialect_for

        return dialect_for(self._db).translate(statement)


def _merge_hits(
    bm25_hits: list[Bm25Hit],
    dense_hits: list[DenseHit],
    bm25_weight: float,
    vector_weight: float,
) -> list[_MergedHit]:
    """Apply the legacy-compatible K=60 reciprocal-rank formula."""
    scores: dict[str, float] = {}
    sources: dict[str, list[str]] = {}
    _add_rrf(scores, sources, [hit.chunk_id for hit in bm25_hits], "bm25", bm25_weight)
    _add_rrf(scores, sources, [hit.chunk_id for hit in dense_hits], "vector", vector_weight)
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
    return [
        _MergedHit(chunk_id, scores[chunk_id], tuple(sources[chunk_id])) for chunk_id in ordered
    ]


def _add_rrf(
    scores: dict[str, float],
    sources: dict[str, list[str]],
    chunk_ids: list[str],
    source: str,
    weight: float,
) -> None:
    """Accumulate one ranked list using RRF K=60."""
    for rank, chunk_id in enumerate(chunk_ids, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (RagService.RRF_K + rank)
        sources.setdefault(chunk_id, []).append(source)


def _to_evidence(
    merged: _MergedHit, row: dict[str, Any], scope: RetrievalScope
) -> RetrievedEvidence:
    """Convert a derived row into a complete provenance-bearing evidence object."""
    chunk_id = str(row["chunk_id"])
    document_id = str(row["document_id"])
    doc_type = str(row["doc_type"])
    content = str(row["content"])
    metadata: dict[str, object] = {
        "doc_type": doc_type,
        "source": str(row["source"]),
        "category": str(row["category"]),
        "url": str(row["url"]),
        "user_id": str(row["user_id"]),
    }
    agent_id = row.get("agent_id")
    if isinstance(agent_id, str) and agent_id:
        metadata["agent_id"] = agent_id
    chunk = KnowledgeChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        content=content,
        index=_chunk_index(chunk_id),
        metadata=metadata,
    )
    document = KnowledgeDocument(
        document_id=document_id,
        doc_type=doc_type if doc_type in {"kb", "source_data"} else "source_data",
        title=str(row["title"]),
        url=str(row["url"]),
        source=str(row["source"]),
        category=str(row["category"]),
        published_at=_optional_text(row.get("published_at")),
        user_id=str(row["user_id"]),
        content_hash=str(row["content_hash"]),
        indexed_at=_optional_text(row.get("indexed_at")),
    )
    source_name: Literal["bm25", "vector", "hybrid"] = (
        "hybrid" if len(merged.sources) > 1 else merged.sources[0]  # type: ignore[assignment]
    )
    evidence_id = hashlib.sha256(f"{document_id}:{chunk_id}".encode()).hexdigest()
    return RetrievedEvidence(
        evidence_id=evidence_id,
        chunk=chunk,
        document=document,
        score=merged.score,
        retrieval_source=source_name,
        scope=scope,
    )


def _chunk_index(chunk_id: str) -> int:
    """Recover the stable KB chunk index when the adapter encoded one."""
    try:
        return int(chunk_id.rsplit(":", maxsplit=1)[-1])
    except ValueError:
        return 0


def _optional_text(value: object) -> str | None:
    """Normalize nullable database text values."""
    return str(value) if value is not None and str(value) else None


__all__ = ["RagService", "RuntimeRagCapabilities"]
