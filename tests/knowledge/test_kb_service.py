"""Integration coverage for local FTS knowledge-base operations."""

import pytest

from multiscribe_agent.knowledge.document_processor import DocumentProcessor
from multiscribe_agent.knowledge.embedding_service import EmbeddingService
from multiscribe_agent.knowledge.kb_service import KBService
from multiscribe_agent.knowledge.retriever import RetrievalHit


@pytest.mark.asyncio
async def test_service_ingests_lists_searches_moves_and_deletes(kb_service, kb_db) -> None:
    """Core CRUD works in dependency-free FTS5 degradation mode."""
    category = await kb_service.create_category("Tech")
    document = await kb_service.ingest_text(
        text="Python retrieval uses FTS5. Python retrieval supports ranking.",
        category_id=category.id,
        name="Retrieval notes",
    )

    assert document.chunk_count == 1
    assert (await kb_service.search("Python"))[0].document_id == document.id
    document_index = await kb_db.fetchone(
        "SELECT name FROM kb_documents_fts WHERE kb_documents_fts MATCH ?", ("Retrieval",)
    )
    assert document_index is not None
    assert document_index["name"] == "Retrieval notes"
    assert (await kb_service.list_categories())[0].document_count == 1
    assert await kb_service.move_to_memory(document.id, "research") == 1
    assert (await kb_db.fetchone("SELECT COUNT(*) AS count FROM agent_memories"))["count"] == 1
    await kb_service.delete_document(document.id)
    assert await kb_service.list_documents() == []


@pytest.mark.asyncio
async def test_service_deduplicates_exact_chunks_and_filters_categories(kb_service) -> None:
    """Exact sha256 duplicate chunks are skipped and category limits retrieval."""
    first = await kb_service.create_category("First")
    second = await kb_service.create_category("Second")
    one = await kb_service.ingest_text(
        text="same searchable content", category_id=first.id, name="one"
    )
    two = await kb_service.ingest_text(
        text="same searchable content", category_id=second.id, name="two"
    )

    assert one.chunk_count == 1
    assert two.chunk_count == 0
    assert await kb_service.search("searchable", category_id=second.id) == []


def test_service_reports_fts_only_capabilities_without_optional_components(kb_service) -> None:
    """The dependency-free service advertises its intended FTS-only degradation state."""
    capabilities = kb_service.capabilities

    assert capabilities.fts_enabled is True
    assert capabilities.vector_enabled is False
    assert capabilities.embedding_enabled is False
    assert capabilities.degraded is True


@pytest.mark.asyncio
async def test_service_similarity_deduplicates_adjacent_document_hits(kb_db) -> None:
    """Injected identical embeddings collapse matching adjacent chunks in one document."""

    class SameVectorEncoder:
        """Return the same vector for all content."""

        def encode(self, texts: list[str], *, normalize_embeddings: bool) -> list[list[float]]:
            """Return normalized duplicate vectors for threshold testing."""
            del normalize_embeddings
            return [[1.0, 0.0] for _ in texts]

    service = KBService(
        kb_db,
        DocumentProcessor(),
        EmbeddingService(SameVectorEncoder()),
        None,
        None,
    )
    first = RetrievalHit("a", "doc", "first", 1.0, ["fts"])
    second = RetrievalHit("b", "doc", "second", 0.9, ["fts"])

    assert await service._deduplicate_hits([first, second], 0.95) == [first]
