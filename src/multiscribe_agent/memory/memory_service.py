"""High-level orchestration for user preferences and memory entries."""

from __future__ import annotations

from multiscribe_agent.domain.models import MemoryEntry
from multiscribe_agent.knowledge.kb_service import KBService
from multiscribe_agent.memory.extractor import PreferenceExtractor
from multiscribe_agent.memory.preference_store import PreferenceStore, UserPreferences
from multiscribe_agent.memory.repositories.memory_entries import MemoryEntryRepository
from multiscribe_agent.memory.retriever import MemoryRetriever


class MemoryService:
    """Coordinate memory CRUD, preference extraction, and KB migration."""

    def __init__(
        self,
        entries: MemoryEntryRepository,
        preferences: PreferenceStore,
        extractor: PreferenceExtractor,
        kb_service: KBService,
    ) -> None:
        """Bind the services required by the memory application boundary."""
        self._entries = entries
        self._preferences = preferences
        self._extractor = extractor
        self._kb_service = kb_service
        self._retriever = MemoryRetriever(entries)

    async def get_preferences(self) -> UserPreferences:
        """Return persisted user preferences."""
        return await self._preferences.load()

    async def save_preferences(self, preferences: UserPreferences) -> None:
        """Persist one complete set of user preferences."""
        await self._preferences.save(preferences)

    async def add_entry(self, entry: MemoryEntry) -> str:
        """Store one entry, returning the existing id on a duplicate."""
        return await self._entries.save(entry)

    async def list_entries(
        self, category: str | None = None, tag: str | None = None, limit: int = 50
    ) -> list[MemoryEntry]:
        """List entries filtered by category and tag."""
        return await self._entries.list(category, tag, limit)

    async def delete_entry(self, entry_id: str) -> bool:
        """Delete one memory record."""
        return await self._entries.delete(entry_id)

    async def search_entries(self, query: str, limit: int = 20) -> list[MemoryEntry]:
        """Search memories through their FTS index."""
        return await self._retriever.search(query, limit)

    async def extract_and_merge(self, days: int = 30) -> int:
        """Extract records from history and persist only new memories."""
        return await self._entries.save_batch(await self._extractor.extract_from_history(days))

    async def move_document_to_memory(self, document_id: str, target_category: str) -> int:
        """Delegate document-chunk migration to the existing KB service."""
        return await self._kb_service.move_to_memory(document_id, target_category)
