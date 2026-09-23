"""Hermetic tests for the P66.3 hybrid retrieval service."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from multiscribe_agent.domain.ports import VectorStorePort
from multiscribe_agent.infra.db import init_db
from multiscribe_agent.knowledge.embedding_service import EmbeddingUnavailableError
from multiscribe_agent.rag.indexing import RagIndexRegistry
from multiscribe_agent.rag.models import KnowledgeChunk, KnowledgeDocument, RetrievalScope
from multiscribe_agent.rag.schema import RagChunksStore
from multiscribe_agent.rag.service import RagService


class FakeVectorStore(VectorStorePort):
    """Deterministic vector port with caller-controlled ranking."""

    def __init__(self, ranked: list[tuple[str, float]]) -> None:
        self.ranked = ranked

    async def upsert(self, chunk_id: str, embedding: Sequence[float]) -> None:
        """Satisfy the storage port for tests that only exercise retrieval."""

    async def delete(self, chunk_id: str) -> None:
        """Satisfy the storage port for tests that only exercise retrieval."""

    async def top_k(self, query: Sequence[float], k: int = 20) -> list[tuple[str, float]]:
        """Return the preconfigured nearest-neighbor order."""
        return self.ranked[:k]


class FakeEmbedder:
    """Query encoder that never touches Hugging Face."""

    async def encode_one(self, text: str) -> list[float]:
        """Return a stable fake vector."""
        return [1.0, 0.0, 0.0]


class BrokenEmbedder:
    """Embedding failure used to verify BM25-only degradation."""

    async def encode_one(self, text: str) -> list[float]:
        """Raise the public embedding-unavailable error."""
        raise EmbeddingUnavailableError("offline")


class FakeReranker:
    """Reverse candidates to prove the post-RRF reranker hook is active."""

    def __init__(self) -> None:
        self.calls = 0

    async def rerank(self, query, evidence, *, top_k):
        """Return the last candidate first and record the query."""
        del query
        self.calls += 1
        return list(reversed(evidence))[:top_k]


def _document(
    document_id: str,
    *,
    user_id: str = "user-a",
    agent_id: str | None = None,
    category: str = "ai",
    source: str = "rss",
    published_at: str = "2026-09-22T00:00:00+00:00",
    doc_type: str = "source_data",
) -> tuple[KnowledgeDocument, KnowledgeChunk]:
    """Build one canonical document/chunk pair for the derived index."""
    chunk_id = f"{document_id}:0"
    metadata: dict[str, object] = {"user_id": user_id, "category": category, "source": source}
    if agent_id is not None:
        metadata["agent_id"] = agent_id
    content = "中文代理工作流与检索工程实践"
    document = KnowledgeDocument(
        document_id=document_id,
        doc_type=doc_type,  # type: ignore[arg-type]
        title=f"Title {document_id}",
        url=f"https://example.com/{document_id}",
        source=source,
        category=category,
        published_at=published_at,
        user_id=user_id,
        content_hash=f"hash-{document_id}",
    )
    chunk = KnowledgeChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        content=content,
        index=0,
        metadata=metadata,
    )
    return document, chunk


async def _seed(db: object, *pairs: tuple[KnowledgeDocument, KnowledgeChunk]) -> None:
    """Populate registry and RAG content index with deterministic rows."""
    registry = RagIndexRegistry(db)  # type: ignore[arg-type]
    chunks = RagChunksStore(db)  # type: ignore[arg-type]
    await registry.ensure_schema()
    await chunks.ensure_schema()
    for document, chunk in pairs:
        await registry.upsert(
            chunk,
            document,
            indexed_at="2026-09-22T00:00:00+00:00",
            index_version="test",
        )
        await chunks.upsert(chunk, document, indexed_at="2026-09-22T00:00:00+00:00")


@pytest.mark.asyncio
async def test_chinese_bm25_and_evidence_metadata(tmp_path) -> None:
    """The tokenized RAG FTS path retrieves Chinese content with provenance."""
    db = await init_db(str(tmp_path / "rag.sqlite"))
    try:
        document, chunk = _document("source_data:zh")
        await _seed(db, (document, chunk))
        service = RagService(db)

        evidence = await service.retrieve(
            "代理工作流",
            RetrievalScope(user_id="user-a"),
            top_k=5,
        )

        assert [item.chunk.chunk_id for item in evidence] == [chunk.chunk_id]
        assert evidence[0].retrieval_source == "bm25"
        assert evidence[0].document.title == document.title
        assert evidence[0].document.url == document.url
        assert evidence[0].document.source == document.source
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_user_scope_is_hard_isolation(tmp_path) -> None:
    """A user cannot receive another user's indexed chunk."""
    db = await init_db(str(tmp_path / "rag.sqlite"))
    try:
        first, first_chunk = _document("source_data:a", user_id="user-a")
        second, second_chunk = _document("source_data:b", user_id="user-b")
        await _seed(db, (first, first_chunk), (second, second_chunk))

        evidence = await RagService(db).retrieve(
            "代理工作流",
            RetrievalScope(user_id="user-a"),
            top_k=5,
        )

        assert [item.chunk.chunk_id for item in evidence] == [first_chunk.chunk_id]
        assert second_chunk.chunk_id not in {item.chunk.chunk_id for item in evidence}
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_agent_scope_is_soft_filter(tmp_path) -> None:
    """An agent scope only narrows a user's visible rows."""
    db = await init_db(str(tmp_path / "rag.sqlite"))
    try:
        agent_doc, agent_chunk = _document("source_data:agent", agent_id="agent-a")
        general_doc, general_chunk = _document("source_data:general")
        await _seed(db, (agent_doc, agent_chunk), (general_doc, general_chunk))

        service = RagService(db)
        unscoped = await service.retrieve(
            "代理工作流",
            RetrievalScope(user_id="user-a"),
            top_k=5,
        )
        evidence = await service.retrieve(
            "代理工作流",
            RetrievalScope(user_id="user-a", agent_id="agent-a"),
            top_k=5,
        )

        assert [item.chunk.chunk_id for item in evidence] == [agent_chunk.chunk_id]
        assert {item.chunk.chunk_id for item in evidence} <= {
            item.chunk.chunk_id for item in unscoped
        }
        assert general_chunk.chunk_id not in {item.chunk.chunk_id for item in evidence}
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_hybrid_rrf_marks_both_sources(tmp_path) -> None:
    """A candidate present in both ranked lists is labelled hybrid."""
    db = await init_db(str(tmp_path / "rag.sqlite"))
    try:
        document, chunk = _document("source_data:hybrid")
        await _seed(db, (document, chunk))
        service = RagService(
            db,
            FakeVectorStore([(chunk.chunk_id, 0.1)]),
            FakeEmbedder(),
        )

        evidence = await service.retrieve(
            "代理工作流",
            RetrievalScope(user_id="user-a"),
            top_k=5,
        )

        assert evidence[0].retrieval_source == "hybrid"
        assert service.capabilities().as_dict()["index_ready"] is True
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_reranker_runs_after_rrf_and_respects_top_k(tmp_path) -> None:
    """Injected rerankers receive fused evidence and control final ordering."""
    db = await init_db(str(tmp_path / "rag.sqlite"))
    try:
        first, first_chunk = _document("source_data:first")
        second, second_chunk = _document("source_data:second")
        await _seed(db, (first, first_chunk), (second, second_chunk))
        reranker = FakeReranker()
        service = RagService(db, reranker=reranker, candidate_k=5)

        evidence = await service.retrieve(
            "代理工作流",
            RetrievalScope(user_id="user-a"),
            top_k=1,
        )

        assert reranker.calls == 1
        assert len(evidence) == 1
        assert evidence[0].chunk.chunk_id == second_chunk.chunk_id
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_vector_failure_degrades_to_bm25(tmp_path) -> None:
    """Embedding failure leaves keyword retrieval available and marks degraded."""
    db = await init_db(str(tmp_path / "rag.sqlite"))
    try:
        document, chunk = _document("source_data:degraded")
        await _seed(db, (document, chunk))
        service = RagService(
            db,
            FakeVectorStore([(chunk.chunk_id, 0.1)]),
            BrokenEmbedder(),
        )

        evidence = await service.retrieve(
            "代理工作流",
            RetrievalScope(user_id="user-a"),
            top_k=5,
        )

        assert [item.chunk.chunk_id for item in evidence] == [chunk.chunk_id]
        assert evidence[0].retrieval_source == "bm25"
        assert service.capabilities().degraded is True
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_category_source_time_and_doc_type_filters(tmp_path) -> None:
    """All optional scope filters are enforced before evidence assembly."""
    db = await init_db(str(tmp_path / "rag.sqlite"))
    try:
        kept, kept_chunk = _document(
            "kb:kept",
            category="engineering",
            source="docs",
            published_at="2026-09-20T00:00:00+00:00",
            doc_type="kb",
        )
        removed, removed_chunk = _document(
            "source_data:removed",
            category="news",
            source="rss",
            published_at="2026-09-10T00:00:00+00:00",
        )
        await _seed(db, (kept, kept_chunk), (removed, removed_chunk))

        evidence = await RagService(db).retrieve(
            "代理工作流",
            RetrievalScope(
                user_id="user-a",
                categories=["engineering"],
                sources=["docs"],
                doc_types=["kb"],
                time_from="2026-09-19T00:00:00+00:00",
                time_to="2026-09-21T00:00:00+00:00",
            ),
            top_k=5,
        )

        assert [item.chunk.chunk_id for item in evidence] == [kept_chunk.chunk_id]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_vector_only_path_returns_vector_source(tmp_path) -> None:
    """A vector hit remains usable when BM25 has no matching terms."""
    db = await init_db(str(tmp_path / "rag.sqlite"))
    try:
        document, chunk = _document("source_data:vector-only")
        await _seed(db, (document, chunk))
        service = RagService(
            db,
            FakeVectorStore([(chunk.chunk_id, 0.2)]),
            FakeEmbedder(),
        )

        evidence = await service.retrieve(
            "完全不同的查询",
            RetrievalScope(user_id="user-a"),
            top_k=5,
        )

        assert [item.chunk.chunk_id for item in evidence] == [chunk.chunk_id]
        assert evidence[0].retrieval_source == "vector"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_missing_fts_reports_index_not_ready(tmp_path) -> None:
    """A missing RAG FTS table returns a capability signal instead of raising."""
    db = await init_db(str(tmp_path / "rag.sqlite"))
    try:
        document, chunk = _document("source_data:missing-fts")
        await _seed(db, (document, chunk))
        await db.execute("DROP TABLE rag_chunks_fts")
        service = RagService(db)

        assert await service.retrieve("代理工作流", RetrievalScope(user_id="user-a")) == []
        capabilities = service.capabilities()
        assert capabilities.as_dict()["index_ready"] is False
        assert capabilities.degraded is True
    finally:
        await db.close()
