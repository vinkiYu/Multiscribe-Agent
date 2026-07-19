"""Coverage for sqlite-vec unavailable and dimension guard paths."""

import pytest

from multiscribe_agent.knowledge.vector_store import VectorStore, VectorStoreUnavailable


@pytest.mark.asyncio
async def test_vector_store_requires_expected_dimension(kb_db) -> None:
    """Malformed vectors fail before a database operation."""
    store = VectorStore(kb_db, dim=2)
    with pytest.raises(ValueError, match="dimensions"):
        await store.upsert("chunk", [1.0])


@pytest.mark.asyncio
async def test_vector_store_falls_back_when_vec_table_is_missing(kb_db) -> None:
    """sqlite-vec search failure is represented as the documented domain signal."""
    store = VectorStore(kb_db, dim=2)
    with pytest.raises(VectorStoreUnavailable):
        await store.top_k([0.0, 1.0])
