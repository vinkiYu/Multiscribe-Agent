"""Protocol-only ports for the backend-neutral RAG subsystem."""

from __future__ import annotations

from typing import Protocol

from multiscribe_agent.rag.models import (
    KnowledgeDocument,
    RagCapabilities,
    RetrievalScope,
    RetrievedEvidence,
)


class RetrievalPort(Protocol):
    """Retrieve provenance-bearing evidence within an explicit user scope."""

    async def retrieve(
        self, query: str, scope: RetrievalScope, *, top_k: int = 10
    ) -> list[RetrievedEvidence]:
        """Return at most ``top_k`` evidence records for the query."""
        ...


class RagServiceProtocol(RetrievalPort, Protocol):
    """Frozen application contract implemented by the later RAG phases."""

    async def index_document(self, doc: KnowledgeDocument) -> int:
        """Index a canonical document and return the number of chunks."""
        ...

    async def rebuild_index(self, doc_types: list[str]) -> None:
        """Rebuild the selected document types with resumable implementations."""
        ...

    def capabilities(self) -> RagCapabilities:
        """Describe available retrieval features and degraded state."""
        ...


# Friendly alias for callers that use the service name rather than the
# explicit Protocol suffix.  Keeping both names avoids forcing an adapter to
# depend on a concrete implementation.
RagService = RagServiceProtocol

__all__ = ["RagService", "RagServiceProtocol", "RetrievalPort"]
