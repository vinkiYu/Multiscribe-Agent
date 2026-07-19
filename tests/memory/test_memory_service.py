"""Service orchestration tests for extraction and KB migration."""

from __future__ import annotations

import pytest

from multiscribe_agent.core.publish_history import PublishHistory
from multiscribe_agent.domain.models import AIResponse
from multiscribe_agent.knowledge.document_processor import DocumentProcessor
from multiscribe_agent.knowledge.kb_service import KBService
from multiscribe_agent.knowledge.retriever import Retriever
from multiscribe_agent.memory.extractor import PreferenceExtractor
from multiscribe_agent.memory.memory_service import MemoryService
from multiscribe_agent.memory.preference_store import PreferenceStore
from multiscribe_agent.memory.repositories.memory_categories import MemoryCategoryRepository
from multiscribe_agent.memory.repositories.memory_entries import MemoryEntryRepository


class FakeTagProvider:
    """Return deterministic LLM tag JSON without network activity."""

    async def generate(self, *args, **kwargs) -> AIResponse:
        """Return one JSON tag array for the extractor contract."""
        del args, kwargs
        return AIResponse(content='["llm-tag"]')


@pytest.mark.asyncio
async def test_extract_and_merge_and_move_document(memory_db) -> None:
    """History extraction deduplicates and KB chunks move into memory storage."""
    history = PublishHistory()
    await history.add(memory_db, "feishu_bot", "success", "AI News", "published content", {})
    kb = KBService(memory_db, DocumentProcessor(), None, None, Retriever(memory_db))
    category = await kb.create_category("Memory")
    document = await kb.ingest_text(
        text="A knowledge document for memory migration.",
        category_id=category.id,
        name="Note",
    )
    service = MemoryService(
        MemoryEntryRepository(memory_db),
        PreferenceStore(MemoryCategoryRepository(memory_db)),
        PreferenceExtractor(memory_db, history),
        kb,
    )
    assert await service.extract_and_merge() == 1
    assert await service.extract_and_merge() == 0
    assert await service.move_document_to_memory(document.id, "kb") == 1
    assert len(await service.list_entries()) == 2


@pytest.mark.asyncio
async def test_extractor_merges_optional_llm_tags(memory_db) -> None:
    """LLM JSON tags augment the deterministic source-derived tag set."""
    history = PublishHistory()
    await history.add(memory_db, "feishu_bot", "success", "AI News", "content", {})
    entries = await PreferenceExtractor(
        memory_db, history, FakeTagProvider()
    ).extract_from_history()
    assert entries[0].tags[-1] == "llm-tag"
