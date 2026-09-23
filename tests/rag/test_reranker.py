"""Hermetic tests for optional RAG cross-encoder reranking."""

from __future__ import annotations

import pytest

from multiscribe_agent.rag.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    RetrievalScope,
    RetrievedEvidence,
)
from multiscribe_agent.rag.reranker import CrossEncoderReranker


class FakeCrossEncoder:
    """Return deterministic relevance scores for query/document pairs."""

    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.calls = 0

    def predict(self, sentences: list[tuple[str, str]]) -> list[float]:
        """Record one batch and return its configured scores."""
        self.calls += 1
        assert len(sentences) == len(self.scores)
        return self.scores


class MalformedCrossEncoder(FakeCrossEncoder):
    """Return too few scores without failing inside the fake itself."""

    def predict(self, sentences: list[tuple[str, str]]) -> list[float]:
        """Return the malformed score list for validation coverage."""
        self.calls += 1
        del sentences
        return self.scores


def _evidence(evidence_id: str, content: str) -> RetrievedEvidence:
    """Build a complete provenance-bearing evidence record."""
    document = KnowledgeDocument(
        document_id=f"doc-{evidence_id}",
        doc_type="kb",
        title=evidence_id,
        url=f"https://example.test/{evidence_id}",
        source="fixture",
        category="ai",
        user_id="admin",
        content_hash=f"hash-{evidence_id}",
    )
    chunk = KnowledgeChunk(
        chunk_id=f"chunk-{evidence_id}",
        document_id=document.document_id,
        content=content,
        index=0,
    )
    return RetrievedEvidence(
        evidence_id=evidence_id,
        chunk=chunk,
        document=document,
        score=0.1,
        retrieval_source="hybrid",
        scope=RetrievalScope(user_id="admin"),
    )


@pytest.mark.asyncio
async def test_cross_encoder_reranker_reorders_and_marks_provenance() -> None:
    """Rerank scores replace RRF scores and expose an explicit provenance suffix."""
    first = _evidence("first", "less relevant")
    second = _evidence("second", "more relevant")
    model = FakeCrossEncoder([0.2, 0.9])

    result = await CrossEncoderReranker(model=model).rerank("query", [first, second], top_k=2)

    assert [item.evidence_id for item in result] == ["second", "first"]
    assert result[0].score == pytest.approx(0.9)
    assert result[0].retrieval_source == "hybrid:reranked"
    assert model.calls == 1


@pytest.mark.asyncio
async def test_cross_encoder_reranker_validates_score_count() -> None:
    """A malformed model response fails instead of silently truncating evidence."""
    model = MalformedCrossEncoder([0.2])
    with pytest.raises(ValueError, match="returned 1 scores for 2 evidence"):
        await CrossEncoderReranker(model=model).rerank(
            "query", [_evidence("first", "one"), _evidence("second", "two")], top_k=2
        )
