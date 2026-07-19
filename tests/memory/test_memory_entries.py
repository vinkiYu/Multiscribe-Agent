"""Repository tests for durable memories and FTS triggers."""

from __future__ import annotations

import pytest

from multiscribe_agent.domain.models import MemoryEntry
from multiscribe_agent.memory.repositories.memory_entries import MemoryEntryRepository


def _entry(entry_id: str, content: str, url: str = "https://example.test") -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        content=content,
        importance=7,
        tags=["ai", "news"],
        created_at=1,
        metadata={"url": url, "category_id": "daily"},
    )


@pytest.mark.asyncio
async def test_save_deduplicates_by_url_and_content(entry_repo: MemoryEntryRepository) -> None:
    """A duplicate hash returns the first canonical identifier and inserts only once."""
    assert await entry_repo.save(_entry("first", "same")) == "first"
    assert await entry_repo.save(_entry("second", "same")) == "first"
    assert [entry.id for entry in await entry_repo.list()] == ["first"]


@pytest.mark.asyncio
async def test_list_filters_and_fts_search(entry_repo: MemoryEntryRepository) -> None:
    """Category, tag, and FTS paths return the typed matching memory."""
    await entry_repo.save(_entry("one", "Python memory retrieval"))
    await entry_repo.save(_entry("two", "Other entry", "https://two.test"))
    assert [entry.id for entry in await entry_repo.list(category_id="daily", tag="ai")] == [
        "two",
        "one",
    ]
    assert [entry.id for entry in await entry_repo.fts_search("Python")] == ["one"]


@pytest.mark.asyncio
async def test_delete_updates_fts(entry_repo: MemoryEntryRepository) -> None:
    """Deleting a record removes it from the trigger-maintained FTS index."""
    await entry_repo.save(_entry("one", "Unique memory phrase"))
    assert await entry_repo.delete("one") is True
    assert await entry_repo.fts_search("Unique") == []


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown_entry(entry_repo: MemoryEntryRepository) -> None:
    """Unknown durable-memory ids have an explicit empty result."""
    assert await entry_repo.get("missing") is None
