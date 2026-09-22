"""Hermetic tests for the P66 indexing pipeline and registry."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from multiscribe_agent.domain.ports import VectorStorePort
from multiscribe_agent.infra.db import init_db
from multiscribe_agent.knowledge.vector_store import VectorStore
from multiscribe_agent.rag.adapter import RagDocumentAdapter
from multiscribe_agent.rag.indexing import RagIndexingPipeline, RagIndexRegistry


class FakeEmbedder:
    """Deterministic encoder that never downloads a real model."""

    def __init__(self, *, fail_marker: str = "") -> None:
        self.fail_marker = fail_marker
        self.calls: list[list[str]] = []

    async def encode(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        if self.fail_marker and any(self.fail_marker in text for text in texts):
            raise RuntimeError("synthetic embedding failure")
        return [[float(len(text)), 0.0, 0.0] for text in texts]


class FakeVectorStore(VectorStorePort):
    """In-memory VectorStorePort used to inspect writes and deletes."""

    def __init__(self) -> None:
        self.values: dict[str, tuple[float, ...]] = {}

    async def upsert(self, chunk_id: str, embedding: Sequence[float]) -> None:
        self.values[chunk_id] = tuple(embedding)

    async def delete(self, chunk_id: str) -> None:
        self.values.pop(chunk_id, None)

    async def top_k(self, query: Sequence[float], k: int = 20) -> list[tuple[str, float]]:
        return [(chunk_id, 0.0) for chunk_id in list(self.values)[:k]]


class WideFakeEmbedder:
    """Fake 384-dimensional encoder for the sqlite-vec smoke test."""

    async def encode(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] * 384 for _ in texts]


def _adapted(description: str = "first", *, source_id: str = "source-1"):
    from datetime import UTC, datetime

    from multiscribe_agent.domain.models import SourceData

    now = datetime(2026, 9, 22, tzinfo=UTC).isoformat()
    row = SourceData(
        id=source_id,
        title="One",
        url="https://example.com/one",
        description=description,
        published_date=now,
        source="example",
        category="ai",
        fetched_at=now,
        ingestion_date=now,
        adapter_name="rss",
    )
    return RagDocumentAdapter(source_window_days=3650).adapt_source_data(
        row, now=datetime(2026, 9, 22, tzinfo=UTC)
    )


@pytest.mark.asyncio
async def test_registry_and_incremental_indexing(tmp_path) -> None:
    """New, unchanged, and changed content follow the hash-based policy."""
    db = await init_db(str(tmp_path / "rag.sqlite"))
    try:
        vector_store = FakeVectorStore()
        registry = RagIndexRegistry(db)
        embedder = FakeEmbedder()
        pipeline = RagIndexingPipeline(vector_store, registry, embedder)
        first = _adapted()
        assert first is not None

        initial = await pipeline.index([first], index_version="v1")
        unchanged = await pipeline.index([first], index_version="v1")
        changed_doc = _adapted("changed")
        assert changed_doc is not None
        changed = await pipeline.index([changed_doc], index_version="v1")

        assert len(initial.indexed_chunk_ids) == 1
        assert len(unchanged.skipped_chunk_ids) == 1
        assert len(changed.indexed_chunk_ids) == 1
        assert len(await registry.get_by_document(first.document.document_id)) == 1
        rag_chunk = await db.fetchone(
            "SELECT chunk_id FROM rag_chunks WHERE chunk_id = ?",
            (first.chunks[0].chunk_id,),
        )
        assert rag_chunk is not None
        assert len(vector_store.values) == 1
        assert len(embedder.calls) >= 2
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_embedding_failure_isolated_to_one_document(tmp_path) -> None:
    """A failed source document does not block another document in the batch."""
    db = await init_db(str(tmp_path / "rag.sqlite"))
    try:
        first = _adapted("good")
        second = _adapted("bad")
        assert first is not None
        assert second is not None
        second = second.__class__(
            document=second.document.model_copy(update={"document_id": "source_data:source-2"}),
            chunks=tuple(
                chunk.model_copy(
                    update={
                        "chunk_id": "source_data:source-2:0",
                        "document_id": "source_data:source-2",
                        "content": "bad item",
                    }
                )
                for chunk in second.chunks
            ),
        )
        vector_store = FakeVectorStore()
        pipeline = RagIndexingPipeline(
            vector_store,
            RagIndexRegistry(db),
            FakeEmbedder(fail_marker="bad"),
        )
        report = await pipeline.index([first, second], index_version="v1")

        assert first.chunks[0].chunk_id in report.indexed_chunk_ids
        assert second.document.document_id in report.failed_document_ids
        assert second.chunks[0].chunk_id not in vector_store.values
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_sqlite_vec_receives_indexed_embedding(tmp_path) -> None:
    """The production VectorStorePort receives vectors, not only registry rows."""
    db = await init_db(str(tmp_path / "rag.sqlite"))
    try:
        adapted = _adapted("sqlite vec")
        assert adapted is not None
        pipeline = RagIndexingPipeline(
            VectorStore(db),
            RagIndexRegistry(db),
            WideFakeEmbedder(),
        )
        report = await pipeline.index([adapted], index_version="v1")

        assert report.indexed_chunk_ids == (adapted.chunks[0].chunk_id,)
        row = await db.fetchone(
            "SELECT chunk_id FROM kb_chunks_vec WHERE chunk_id = ?",
            (adapted.chunks[0].chunk_id,),
        )
        assert row is not None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_prune_source_documents_deletes_vector_and_registry_rows(tmp_path) -> None:
    """SourceData outside the active window is removed from both stores."""
    db = await init_db(str(tmp_path / "rag.sqlite"))
    try:
        first = _adapted("keep", source_id="source-1")
        second = _adapted("remove", source_id="source-2")
        assert first is not None
        assert second is not None
        vector_store = FakeVectorStore()
        registry = RagIndexRegistry(db)
        pipeline = RagIndexingPipeline(vector_store, registry, FakeEmbedder())

        await pipeline.index([first, second], index_version="v1")
        deleted = await pipeline.prune_source_documents({first.document.document_id})

        assert deleted == (second.chunks[0].chunk_id,)
        assert second.chunks[0].chunk_id not in vector_store.values
        assert await registry.get_by_document(second.document.document_id) == []
        assert (
            await db.fetchone(
                "SELECT chunk_id FROM rag_chunks WHERE chunk_id = ?",
                (second.chunks[0].chunk_id,),
            )
            is None
        )
        assert await registry.get_by_document(first.document.document_id)
    finally:
        await db.close()
