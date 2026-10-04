"""Coverage for Qdrant availability, dimension guards, and point lifecycle."""

from __future__ import annotations

import pytest

from multiscribe_agent.knowledge.vector_store import QdrantVectorStore
from tests.db import get_test_qdrant_url


@pytest.fixture
def qdrant_url() -> str:
    """Return the configured Qdrant endpoint or a lazily started container."""
    return get_test_qdrant_url()


@pytest.mark.asyncio
async def test_vector_store_requires_expected_dimension(qdrant_url) -> None:
    """Malformed vectors fail before any network operation."""
    store = QdrantVectorStore(qdrant_url, dim=2, collection="rag_vectors_dim_guard")
    try:
        with pytest.raises(ValueError, match="dimensions"):
            await store.upsert("chunk", [1.0])
        with pytest.raises(ValueError, match="dimensions"):
            await store.top_k([1.0])
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_vector_store_returns_empty_for_empty_collection(qdrant_url) -> None:
    """A lazily created collection returns no hits when it is empty."""
    store = QdrantVectorStore(qdrant_url, dim=2, collection="rag_vectors_dim_guard")
    try:
        assert await store.top_k([0.0, 1.0]) == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_vector_store_upsert_top_k_and_delete_round_trip(qdrant_url) -> None:
    """Upsert is idempotent, retrieval finds the nearest point, delete removes it."""
    store = QdrantVectorStore(qdrant_url, dim=2, collection="rag_vectors_round_trip")
    try:
        await store.upsert("chunk-1", [1.0, 0.0])
        await store.upsert("chunk-1", [1.0, 0.0])
        await store.upsert("chunk-2", [0.0, 1.0])

        hits = await store.top_k([1.0, 0.0], k=2)
        assert [chunk_id for chunk_id, _distance in hits] == ["chunk-1", "chunk-2"]
        assert hits[0][1] == pytest.approx(0.0, abs=1e-6)

        await store.delete("chunk-1")
        remaining = await store.top_k([1.0, 0.0], k=2)
        assert [chunk_id for chunk_id, _distance in remaining] == ["chunk-2"]
        assert await store.count() == 1
    finally:
        await store.close()
