"""PostgreSQL schema for the P66 RAG index manifest."""

from __future__ import annotations

RAG_INDEX_REGISTRY_TABLE = """
CREATE TABLE IF NOT EXISTS rag_index_registry (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    user_id TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    index_version TEXT NOT NULL
)
"""

RAG_INDEX_REGISTRY_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_rag_index_registry_document ON rag_index_registry(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_rag_index_registry_type ON rag_index_registry(doc_type)",
)
