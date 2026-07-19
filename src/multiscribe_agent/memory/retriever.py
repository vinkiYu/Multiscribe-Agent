"""Memory-specific FTS facade."""

from __future__ import annotations

from multiscribe_agent.domain.models import MemoryEntry
from multiscribe_agent.memory.repositories.memory_entries import MemoryEntryRepository


class MemoryRetriever:
    """Expose search over the existing agent-memory FTS index."""

    def __init__(self, entries: MemoryEntryRepository) -> None:
        """Create a search facade over a memory repository."""
        self._entries = entries

    async def search(self, query: str, limit: int = 20) -> list[MemoryEntry]:
        """Return FTS-ranked memory entries."""
        return await self._entries.fts_search(query, limit)
