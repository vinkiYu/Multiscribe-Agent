"""Shared PostgreSQL and knowledge-service fixtures."""

from __future__ import annotations

import pytest_asyncio

from multiscribe_agent.infra.db import Database
from multiscribe_agent.knowledge.document_processor import DocumentProcessor
from multiscribe_agent.knowledge.kb_service import KBService
from tests.db import init_test_database


@pytest_asyncio.fixture
async def kb_db():
    """Provide an initialized clean PostgreSQL database."""
    db = await init_test_database()
    try:
        yield db
    finally:
        await db.close()


@pytest_asyncio.fixture
async def kb_service(kb_db: Database) -> KBService:
    """Provide the persistence-only knowledge service for CRUD tests."""
    return KBService(kb_db, DocumentProcessor(), None, None)
