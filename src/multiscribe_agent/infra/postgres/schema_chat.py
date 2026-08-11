"""PostgreSQL DDL for chat sessions and messages."""

from __future__ import annotations

CHAT_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
"""

CHAT_SESSIONS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated ON chat_sessions(updated_at DESC)"
)

CHAT_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
"""

CHAT_MESSAGES_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at)"
)


ALL_CHAT_SCHEMAS = (
    CHAT_SESSIONS_TABLE,
    CHAT_SESSIONS_INDEX,
    CHAT_MESSAGES_TABLE,
    CHAT_MESSAGES_INDEX,
)
