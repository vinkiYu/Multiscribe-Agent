"""Reusable Memory/Knowledge retrieval middleware for every Agent entry point."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from multiscribe_agent.knowledge.kb_service import KBService
from multiscribe_agent.memory.memory_service import MemoryService


@dataclass(frozen=True, slots=True)
class RetrievedContext:
    memories: list[str] = field(default_factory=list)
    knowledge: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


class ContextProvider(Protocol):
    async def retrieve(self, query: str, *, agent_id: str) -> RetrievedContext: ...


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

    async def retrieve(self, query: str, *, agent_id: str) -> RetrievedContext:
        del agent_id
        memories: list[str] = []
        knowledge: list[str] = []
        reasons: list[str] = []
        if self._memory is not None:
            try:
                entries = await self._memory.search_entries(query, self._top_k)
                memories = self._bounded([entry.content for entry in entries])
                reasons.extend("memory:fts" for _ in memories)
            except Exception:  # Retrieval is an optional enhancement boundary.
                reasons.append("memory:degraded")
        if self._knowledge is not None:
            try:
                hits = await self._knowledge.search(query, top_k=self._top_k)
                knowledge = self._bounded([hit.content for hit in hits])
                reasons.extend("knowledge:hybrid" for _ in knowledge)
            except Exception:  # Retrieval is an optional enhancement boundary.
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
