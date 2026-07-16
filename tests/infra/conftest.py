"""Shared in-memory SQLite fixture for infrastructure tests."""

from collections.abc import AsyncIterator

import pytest_asyncio

from multiscribe_agent.infra.db import Database, init_db


@pytest_asyncio.fixture
async def db() -> AsyncIterator[Database]:
    """Provide an initialized in-memory database and close it after each test."""
    database = await init_db(":memory:")
    try:
        yield database
    finally:
        await database.close()
