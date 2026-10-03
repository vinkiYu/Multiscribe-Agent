"""Shared PostgreSQL fixture for infrastructure tests."""

from collections.abc import AsyncIterator

import pytest_asyncio

from multiscribe_agent.infra.db import Database
from tests.db import init_test_database


@pytest_asyncio.fixture
async def db() -> AsyncIterator[Database]:
    """Provide an initialized clean PostgreSQL database and close it after each test."""
    database = await init_test_database()
    try:
        yield database
    finally:
        await database.close()
