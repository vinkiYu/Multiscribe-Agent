"""Dedicated memory-category repository coverage."""

from __future__ import annotations

import pytest

from multiscribe_agent.domain.models import MemoryEntry
from multiscribe_agent.memory.repositories.memory_categories import MemoryCategoryRepository
from multiscribe_agent.memory.repositories.memory_entries import MemoryEntryRepository


@pytest.mark.asyncio
async def test_category_repository_crud(category_repo: MemoryCategoryRepository) -> None:
    """Category JSON persists, lists with its id, and deletes cleanly."""
    await category_repo.save("topic", {"name": "Topic"})
    assert await category_repo.get("topic") == {"name": "Topic"}
    assert await category_repo.list_all() == [{"id": "topic", "name": "Topic"}]
    assert await category_repo.delete("topic") is True
    assert await category_repo.get("topic") is None


@pytest.mark.asyncio
async def test_save_batch_counts_only_unique_entries(entry_repo: MemoryEntryRepository) -> None:
    """Batch persistence counts only new content hashes."""
    first = MemoryEntry(
        id="first",
        content="Duplicate content",
        importance=5,
        tags=[],
        created_at=1,
        metadata={},
    )
    duplicate = first.model_copy(update={"id": "second"})
    assert await entry_repo.save_batch([first, duplicate]) == 1
