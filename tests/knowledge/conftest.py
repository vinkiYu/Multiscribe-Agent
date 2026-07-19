"""Shared local SQLite and knowledge-service fixtures."""

from __future__ import annotations

import pytest_asyncio

from multiscribe_agent.infra.db import Database, init_db
from multiscribe_agent.knowledge.document_processor import DocumentProcessor
from multiscribe_agent.knowledge.kb_service import KBService
from multiscribe_agent.knowledge.retriever import Retriever


@pytest_asyncio.fixture
async def kb_db():
    """Provide initialized in-memory SQLite with the P16 migration applied."""
    db = await init_db(":memory:")
    try:
        yield db
    finally:
        await db.close()


@pytest_asyncio.fixture
async def kb_service(kb_db: Database) -> KBService:
    """Provide the FTS5-only knowledge service expected in dependency-free CI."""
    return KBService(kb_db, DocumentProcessor(), None, None, Retriever(kb_db))
