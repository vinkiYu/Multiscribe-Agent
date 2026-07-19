"""Shared in-memory fixtures for memory-service tests."""

from __future__ import annotations

import pytest_asyncio

from multiscribe_agent.infra.db import Database, init_db
from multiscribe_agent.memory.repositories.memory_categories import MemoryCategoryRepository
from multiscribe_agent.memory.repositories.memory_entries import MemoryEntryRepository


@pytest_asyncio.fixture
async def memory_db() -> Database:
    """Provide a fresh initialized in-memory SQLite database."""
    db = await init_db(":memory:")
    try:
        yield db
    finally:
        await db.close()


@pytest_asyncio.fixture
async def entry_repo(memory_db: Database) -> MemoryEntryRepository:
    """Provide the dedicated durable-memory repository."""
    return MemoryEntryRepository(memory_db)


@pytest_asyncio.fixture
async def category_repo(memory_db: Database) -> MemoryCategoryRepository:
    """Provide the dedicated durable-category repository."""
    return MemoryCategoryRepository(memory_db)
