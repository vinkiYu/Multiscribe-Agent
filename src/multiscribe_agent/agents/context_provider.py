"""Reusable Memory/Knowledge retrieval middleware for every Agent entry point."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import structlog

from multiscribe_agent.knowledge.kb_service import KBService
from multiscribe_agent.memory.memory_service import MemoryService
from multiscribe_agent.rag.models import RetrievalScope, RetrievedEvidence
from multiscribe_agent.rag.ports import RagServiceProtocol

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RetrievedContext:
    memories: list[str] = field(default_factory=list)
    knowledge: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    evidence: list[RetrievedEvidence] = field(default_factory=list)


class ContextProvider(Protocol):
    async def retrieve(
        self, query: str, *, agent_id: str, user_id: str | None = None
    ) -> RetrievedContext: ...


class MemoryKnowledgeContextProvider:
    """Best-effort bounded retrieval over the existing local services."""

    def __init__(
        self,
        memory: MemoryService | None,
        knowledge: KBService | None,
        *,
        top_k: int = 5,
        max_chars: int = 2_400,
    ) -> None:
        self._memory = memory
        self._knowledge = knowledge
        self._top_k = top_k
        self._max_chars = max_chars

    async def retrieve(
        self, query: str, *, agent_id: str, user_id: str | None = None
    ) -> RetrievedContext:
        _ = (agent_id, user_id)
        memories: list[str] = []
        knowledge: list[str] = []
        reasons: list[str] = []
        if self._memory is not None:
            try:
                entries = await self._memory.search_entries(query, self._top_k)
                memories = self._bounded([entry.content for entry in entries])
                reasons.extend("memory:fts" for _ in memories)
            except Exception as exc:  # Retrieval is an optional enhancement boundary.
                log.warning(
                    "context_provider_memory_degraded",
                    query_prefix=query[:80],
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:200],
                )
                reasons.append("memory:degraded")
        if self._knowledge is not None:
            try:
                hits = await self._knowledge.search(query, top_k=self._top_k)
                knowledge = self._bounded([hit.content for hit in hits])
                reasons.extend("knowledge:hybrid" for _ in knowledge)
            except Exception as exc:  # Retrieval is an optional enhancement boundary.
                log.warning(
                    "context_provider_knowledge_degraded",
                    query_prefix=query[:80],
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:200],
                )
                reasons.append("knowledge:degraded")
        return RetrievedContext(memories, knowledge, reasons)

    def _bounded(self, values: list[str]) -> list[str]:
        selected: list[str] = []
        used = 0
        seen: set[str] = set()
        for value in values:
            normalized = " ".join(value.split())
            if not normalized or normalized in seen:
                continue
            remaining = self._max_chars - used
            if remaining <= 0:
                break
            selected.append(normalized[:remaining])
            used += len(selected[-1])
            seen.add(normalized)
        return selected


class RagContextProvider:
    """Best-effort Agent context provider backed by the P66 RAG service."""

    def __init__(
        self,
        rag: RagServiceProtocol,
        *,
        default_user_id: str = "admin",
        top_k: int = 5,
        max_chars: int = 2_400,
    ) -> None:
        """Bind the RAG service and the fallback owner for non-API callers."""
        if not default_user_id.strip():
            raise ValueError("default_user_id must not be empty")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")
        self._rag = rag
        self._default_user_id = default_user_id.strip()
        self._top_k = top_k
        self._max_chars = max_chars

    async def retrieve(
        self, query: str, *, agent_id: str, user_id: str | None = None
    ) -> RetrievedContext:
        """Retrieve scope-isolated Evidence and retain legacy knowledge strings."""
        resolved_user_id = user_id.strip() if user_id is not None and user_id.strip() else None
        scope = RetrievalScope(
            user_id=resolved_user_id or self._default_user_id,
            agent_id=agent_id.strip() or None,
        )
        try:
            evidence = await self._rag.retrieve(query, scope, top_k=self._top_k)
        except Exception as exc:  # Context enrichment remains best-effort.
            log.warning(
                "context_provider_rag_degraded",
                error_type=type(exc).__name__,
            )
            return RetrievedContext(reasons=["rag:degraded"])

        formatted = [self._format_evidence(item) for item in evidence]
        return RetrievedContext(
            knowledge=self._bounded(formatted),
            reasons=[f"rag:{item.retrieval_source}" for item in evidence],
            evidence=list(evidence),
        )

    def _bounded(self, values: list[str]) -> list[str]:
        """Keep compatibility strings bounded while preserving structured Evidence."""
        selected: list[str] = []
        used = 0
        for value in values:
            remaining = self._max_chars - used
            if remaining <= 0:
                break
            normalized = " ".join(value.split())
            if not normalized:
                continue
            selected.append(normalized[:remaining])
            used += len(selected[-1])
        return selected

    @staticmethod
    def _format_evidence(evidence: RetrievedEvidence) -> str:
        """Render provenance for the legacy string-based Harness injection path."""
        document = evidence.document
        title = document.title.strip() or "Untitled"
        source = document.source.strip() or "unknown-source"
        url = document.url.strip()
        header = f"[{title}] {source}"
        if url:
            header = f"{header} {url}"
        return f"{header}\n{evidence.chunk.content.strip()}"
