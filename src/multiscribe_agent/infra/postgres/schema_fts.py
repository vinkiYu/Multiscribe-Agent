"""PostgreSQL DDL for pgvector and tsvector-backed search tables."""

from __future__ import annotations

PGVECTOR_EXTENSION = "CREATE EXTENSION IF NOT EXISTS vector"

CHUNK_VECTORS_TABLE = """
CREATE TABLE IF NOT EXISTS chunk_vectors (
    chunk_id TEXT PRIMARY KEY,
    embedding vector(384)
)
"""

SOURCE_DATA_FTS_TABLE = """
CREATE TABLE IF NOT EXISTS source_data_fts (
    row_id TEXT PRIMARY KEY REFERENCES source_data(id) ON DELETE CASCADE,
    title_tsv tsvector,
    description_tsv tsvector,
    ai_summary_tsv tsvector
)
"""

SOURCE_DATA_FTS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_sdf_title ON source_data_fts USING GIN(title_tsv)",
    "CREATE INDEX IF NOT EXISTS idx_sdf_desc ON source_data_fts USING GIN(description_tsv)",
    "CREATE INDEX IF NOT EXISTS idx_sdf_ai ON source_data_fts USING GIN(ai_summary_tsv)",
]

KB_CHUNKS_FTS_TABLE = """
CREATE TABLE IF NOT EXISTS kb_chunks_fts (
    chunk_id TEXT PRIMARY KEY REFERENCES kb_chunks(id) ON DELETE CASCADE,
    content_tsv tsvector
)
"""

KB_CHUNKS_FTS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_kcf_content ON kb_chunks_fts USING GIN(content_tsv)"
)

AGENT_MEMORIES_FTS_TABLE = """
CREATE TABLE IF NOT EXISTS agent_memories_fts (
    row_id TEXT PRIMARY KEY REFERENCES agent_memories(id) ON DELETE CASCADE,
    content_tsv tsvector,
    tags_tsv tsvector
)
"""

AGENT_MEMORIES_FTS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_amf_content ON agent_memories_fts USING GIN(content_tsv)",
    "CREATE INDEX IF NOT EXISTS idx_amf_tags ON agent_memories_fts USING GIN(tags_tsv)",
]
