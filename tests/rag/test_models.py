"""Contract tests for P66.1 RAG models and ports."""

from __future__ import annotations

from typing import cast

import pytest

from multiscribe_agent.rag.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    RagCapabilities,
    RetrievalScope,
    RetrievedEvidence,
)
from multiscribe_agent.rag.ports import RagServiceProtocol, RetrievalPort


def _document() -> KnowledgeDocument:
    return KnowledgeDocument(
        document_id="source-001",
        doc_type="source_data",
        title="A retrieval paper",
        url="https://example.test/retrieval",
        source="Example News",
        category="AI",
        published_at="2026-09-22T00:00:00+00:00",
        user_id="user-001",
        content_hash="a" * 64,
        indexed_at="2026-09-22T00:01:00+00:00",
    )


def test_document_chunk_evidence_round_trip() -> None:
    """Nested contracts serialize and validate without losing provenance."""
    document = _document()
    chunk = KnowledgeChunk(
        chunk_id="chunk-001",
        document_id=document.document_id,
        content="Hybrid retrieval combines lexical and dense signals.",
        index=0,
        metadata={"sha256": document.content_hash},
    )
    scope = RetrievalScope(user_id="user-001", agent_id=None, doc_types=["source_data"])
    evidence = RetrievedEvidence(
        evidence_id="evidence-001",
        chunk=chunk,
        document=document,
        score=0.75,
        retrieval_source="hybrid",
        scope=scope,
    )

    restored = RetrievedEvidence.model_validate_json(evidence.model_dump_json())

    assert restored == evidence
    assert restored.document.user_id == "user-001"
    assert restored.chunk.document_id == restored.document.document_id
    assert restored.scope.doc_types == ["source_data"]


def test_scope_requires_user_and_allows_unfiltered_agent() -> None:
    """User isolation is mandatory while agent filtering is optional."""
    scope = RetrievalScope(user_id="user-001")

    assert scope.agent_id is None
    assert scope.categories == []
    assert scope.sources == []
    assert scope.doc_types == []

    with pytest.raises(ValueError, match="user_id must not be empty"):
        RetrievalScope(user_id=" ")


def test_models_reject_empty_identity_and_invalid_scope_type() -> None:
    """Stable identities and the two supported document types are validated."""
    with pytest.raises(ValueError, match="document_id must not be empty"):
        KnowledgeDocument(
            document_id=" ",
            doc_type="kb",
            title="title",
            url="https://example.test",
            source="source",
            category="category",
            user_id="user-001",
            content_hash="hash",
        )

    with pytest.raises(ValueError, match="doc_type"):
        KnowledgeDocument(
            document_id="doc-001",
            doc_type=cast("object", "memory"),
            title="title",
            url="https://example.test",
            source="source",
            category="category",
            user_id="user-001",
            content_hash="hash",
        )


def test_capabilities_expose_degraded_state() -> None:
    """Missing vector or embedding support is represented as Degraded."""
    degraded = RagCapabilities(vector_enabled=False, embedding_enabled=True)
    healthy = RagCapabilities(vector_enabled=True, embedding_enabled=True)

    assert degraded.degraded is True
    assert degraded.as_dict()["degraded"] is True
    assert healthy.degraded is False


def test_fake_implementation_matches_protocols() -> None:
    """A lightweight adapter can satisfy both protocol contracts."""

    class FakeRag:
        async def retrieve(
            self, query: str, scope: RetrievalScope, *, top_k: int = 10
        ) -> list[RetrievedEvidence]:
            del query, scope, top_k
            return []

        async def index_document(self, doc: KnowledgeDocument) -> int:
            return 1 if doc.document_id else 0

        async def rebuild_index(self, doc_types: list[str]) -> None:
            del doc_types

        def capabilities(self) -> RagCapabilities:
            return RagCapabilities()

    fake = FakeRag()
    retrieval_port: RetrievalPort = fake
    rag_port: RagServiceProtocol = fake

    assert retrieval_port is rag_port
