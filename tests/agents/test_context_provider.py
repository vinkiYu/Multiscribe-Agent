"""Observability coverage for best-effort Agent context retrieval."""

from __future__ import annotations

import pytest

import multiscribe_agent.agents.context_provider as context_provider_module
from multiscribe_agent.agents.context_provider import (
    MemoryKnowledgeContextProvider,
    RagContextProvider,
)
from multiscribe_agent.rag.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    RetrievalScope,
    RetrievedEvidence,
)


class _FailingMemory:
    async def search_entries(self, query: str, limit: int) -> list[object]:
        del query, limit
        raise TimeoutError("memory lookup timed out")


class _CapturingLog:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def warning(self, event: str, **kwargs: object) -> None:
        self.calls.append((event, kwargs))


@pytest.mark.asyncio
async def test_memory_failure_is_logged_and_keeps_retrieval_degraded(monkeypatch) -> None:
    """Memory failures remain non-fatal but leave a safe structured diagnostic."""
    log = _CapturingLog()
    monkeypatch.setattr(context_provider_module, "log", log)
    provider = MemoryKnowledgeContextProvider(_FailingMemory(), None)

    result = await provider.retrieve("sensitive query that should be bounded", agent_id="agent-1")

    assert result.memories == []
    assert result.reasons == ["memory:degraded"]
    assert log.calls == [
        (
            "context_provider_memory_degraded",
            {
                "query_prefix": "sensitive query that should be bounded",
                "error_type": "TimeoutError",
                "error_message": "memory lookup timed out",
            },
        )
    ]


class _FakeRag:
    def __init__(self, evidence: list[RetrievedEvidence] | None = None) -> None:
        self.evidence = evidence or []
        self.calls: list[tuple[str, RetrievalScope, int]] = []

    async def retrieve(
        self, query: str, scope: RetrievalScope, *, top_k: int = 10
    ) -> list[RetrievedEvidence]:
        self.calls.append((query, scope, top_k))
        return self.evidence


class _BrokenRag:
    async def retrieve(
        self, query: str, scope: RetrievalScope, *, top_k: int = 10
    ) -> list[RetrievedEvidence]:
        del query, scope, top_k
        raise RuntimeError("rag unavailable")


def _evidence() -> RetrievedEvidence:
    document = KnowledgeDocument(
        document_id="source_data:1",
        doc_type="source_data",
        title="Agent RAG",
        url="https://example.test/rag",
        source="example",
        category="ai",
        user_id="member-1",
        content_hash="a" * 64,
    )
    return RetrievedEvidence(
        evidence_id="e-1",
        chunk=KnowledgeChunk(
            chunk_id="source_data:1:0",
            document_id=document.document_id,
            content="Hybrid retrieval evidence",
            index=0,
        ),
        document=document,
        score=1.0,
        retrieval_source="hybrid",
        scope=RetrievalScope(user_id="member-1"),
    )


@pytest.mark.asyncio
async def test_rag_context_provider_passes_user_and_agent_scope() -> None:
    """RAG context carries the hard user boundary and soft Agent filter."""
    rag = _FakeRag([_evidence()])
    provider = RagContextProvider(rag, default_user_id="admin", top_k=3)

    result = await provider.retrieve("agent", agent_id="agent-1", user_id="member-1")

    assert result.evidence[0].document.title == "Agent RAG"
    assert result.knowledge == [
        "[Agent RAG] example https://example.test/rag Hybrid retrieval evidence"
    ]
    assert result.reasons == ["rag:hybrid"]
    assert len(rag.calls) == 1
    scope = rag.calls[0][1]
    assert scope.user_id == "member-1"
    assert scope.agent_id == "agent-1"
    assert rag.calls[0][2] == 3


@pytest.mark.asyncio
async def test_rag_context_provider_degrades_to_empty_context() -> None:
    """RAG failures do not block the Agent request."""
    result = await RagContextProvider(_BrokenRag()).retrieve("agent", agent_id="agent-1")

    assert result.knowledge == []
    assert result.evidence == []
    assert result.reasons == ["rag:degraded"]


@pytest.mark.asyncio
async def test_rag_context_provider_uses_default_for_blank_user_id() -> None:
    """Whitespace API subjects cannot erase the mandatory user boundary."""
    rag = _FakeRag()
    provider = RagContextProvider(rag, default_user_id="admin")

    await provider.retrieve("agent", agent_id="", user_id="   ")

    scope = rag.calls[0][1]
    assert scope.user_id == "admin"
    assert scope.agent_id is None
