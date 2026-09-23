"""Integration coverage for local FTS knowledge-base operations."""

import pytest


@pytest.mark.asyncio
async def test_service_ingests_lists_moves_and_deletes(kb_service, kb_db) -> None:
    """Core persistence operations work without the optional RAG runtime."""
    category = await kb_service.create_category("Tech")
    document = await kb_service.ingest_text(
        text="Python retrieval uses FTS5. Python retrieval supports ranking.",
        category_id=category.id,
        name="Retrieval notes",
    )

    assert document.chunk_count == 1
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
async def test_service_deduplicates_exact_chunks(kb_service) -> None:
    """Exact sha256 duplicate chunks are skipped during ingestion."""
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


def test_service_reports_fts_only_capabilities_without_optional_components(kb_service) -> None:
    """The dependency-free service advertises its intended FTS-only degradation state."""
    capabilities = kb_service.capabilities

    assert capabilities.fts_enabled is True
    assert capabilities.vector_enabled is False
    assert capabilities.embedding_enabled is False
    assert capabilities.degraded is True
