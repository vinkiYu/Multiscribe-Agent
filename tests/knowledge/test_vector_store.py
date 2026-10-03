"""Coverage for pgvector availability and dimension guard paths."""

import pytest

from multiscribe_agent.knowledge.vector_store import VectorStore


@pytest.mark.asyncio
async def test_vector_store_requires_expected_dimension(kb_db) -> None:
    """Malformed vectors fail before a database operation."""
    store = VectorStore(kb_db, dim=2)
    with pytest.raises(ValueError, match="dimensions"):
        await store.upsert("chunk", [1.0])


@pytest.mark.asyncio
async def test_vector_store_returns_empty_for_empty_pgvector_table(kb_db) -> None:
    """A ready PostgreSQL vector table returns no hits when it is empty."""
    store = VectorStore(kb_db, dim=2)
    assert await store.top_k([0.0, 1.0]) == []
