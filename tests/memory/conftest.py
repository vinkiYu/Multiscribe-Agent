"""Shared PostgreSQL fixtures for memory-service tests."""

from __future__ import annotations

import pytest_asyncio

from multiscribe_agent.infra.db import Database
from multiscribe_agent.memory.repositories.memory_categories import MemoryCategoryRepository
from multiscribe_agent.memory.repositories.memory_entries import MemoryEntryRepository
from tests.db import init_test_database


@pytest_asyncio.fixture
async def memory_db() -> Database:
    """Provide a fresh initialized PostgreSQL database."""
    db = await init_test_database()
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
