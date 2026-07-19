"""Coverage for FTS5 fallback and RRF provenance merging."""

import pytest

from multiscribe_agent.knowledge.retriever import Retriever, _add_rrf


@pytest.mark.asyncio
async def test_retriever_searches_fts_without_optional_vector_components(kb_db) -> None:
    """FTS5 retrieval remains operational when optional vector features are absent."""
    await kb_db.execute(
        "INSERT INTO kb_chunks(id, document_id, content, metadata) VALUES (?, ?, ?, ?)",
        ("c1", "d1", "python knowledge retrieval", "{}"),
    )

    hits = await Retriever(kb_db).search("python")

    assert hits[0].chunk_id == "c1"
    assert hits[0].source == ["fts"]


def test_rrf_accumulates_scores_and_multiple_sources() -> None:
    """The same candidate receives contributions from both ranked lists."""
    scores: dict[str, float] = {}
    sources: dict[str, list[str]] = {}

    _add_rrf(scores, sources, ["a", "b"], "fts", 1.0)
    _add_rrf(scores, sources, ["b"], "vector", 1.0)

    assert scores["b"] > scores["a"]
    assert sources["b"] == ["fts", "vector"]
