"""Persistence for chat sessions and messages with PG/SQLite dialect support."""

from __future__ import annotations

import json
from builtins import list as builtin_list
from time import time
from uuid import uuid4

from multiscribe_agent.domain.models import ChatMessage, ChatSession
from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.dialect import DialectRepositoryMixin


class ChatSessionRepository(DialectRepositoryMixin):
    """CRUD for chat sessions and their messages using backend-neutral SQL."""

    def __init__(self, db: Database) -> None:
        """Bind this repository to an initialized database."""
        self._db = db

    async def create_session(self, title: str = "") -> ChatSession:
        """Create a new empty session and return its persisted form."""
        now = int(time())
        session = ChatSession(
            id=str(uuid4()),
            title=title.strip()[:200],
            created_at=now,
            updated_at=now,
            message_count=0,
        )
        await self._execute(
            "INSERT INTO chat_sessions(id, title, created_at, updated_at, message_count, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session.id,
                session.title,
                session.created_at,
                session.updated_at,
                session.message_count,
                json.dumps(session.metadata, ensure_ascii=False, sort_keys=True),
            ),
        )
        return session

    async def get_session(self, session_id: str) -> ChatSession | None:
        """Return one session by id, or None when missing."""
        row = await self._fetchone(
            "SELECT id, title, created_at, updated_at, message_count, metadata "
            "FROM chat_sessions WHERE id = ?",
            (session_id,),
        )
        return self._session_from_row(row) if row is not None else None

    async def list_sessions(self, limit: int = 50) -> builtin_list[ChatSession]:
        """Return the most-recently-updated sessions in descending order."""
        bounded = max(1, min(limit, 200))
        rows = await self._fetchall(
            "SELECT id, title, created_at, updated_at, message_count, metadata "
            "FROM chat_sessions ORDER BY updated_at DESC LIMIT ?",
            (bounded,),
        )
        return [self._session_from_row(row) for row in rows]

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and cascade-remove its messages."""
        result = await self._execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        return (result or 0) > 0

    async def update_title(self, session_id: str, title: str) -> bool:
        """Replace the session title without touching the message counters."""
        cleaned = title.strip()[:200]
        if not cleaned:
            return False
        result = await self._execute(
            "UPDATE chat_sessions SET title = ? WHERE id = ?",
            (cleaned, session_id),
        )
        return (result or 0) > 0

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> ChatMessage | None:
        """Append a message to an existing session and bump the updated_at timer."""
        if role not in {"user", "assistant", "system"}:
            raise ValueError(f"unsupported chat role: {role!r}")
        if not content or not content.strip():
            raise ValueError("chat message content must not be empty")
        session = await self.get_session(session_id)
        if session is None:
            return None
        now = int(time())
        message = ChatMessage(
            id=str(uuid4()),
            session_id=session_id,
            role=role,
            content=content.strip(),
            created_at=now,
            metadata=metadata or {},
        )
        await self._execute(
            "INSERT INTO chat_messages(id, session_id, role, content, created_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                message.id,
                message.session_id,
                message.role,
                message.content,
                message.created_at,
                json.dumps(message.metadata, ensure_ascii=False, sort_keys=True),
            ),
        )
        await self._execute(
            "UPDATE chat_sessions SET updated_at = ?, message_count = message_count + 1 "
            "WHERE id = ?",
            (now, session_id),
        )
        return message

    async def list_messages(self, session_id: str, limit: int = 200) -> builtin_list[ChatMessage]:
        """Return all messages for a session, ordered chronologically."""
        bounded = max(1, min(limit, 1_000))
        rows = await self._fetchall(
            "SELECT id, session_id, role, content, created_at, metadata "
            "FROM chat_messages WHERE session_id = ? "
            "ORDER BY created_at ASC LIMIT ?",
            (session_id, bounded),
        )
        return [self._message_from_row(row) for row in rows]

    @staticmethod
    def _session_from_row(row: object) -> ChatSession:
        metadata = json.loads(str(row["metadata"]))  # type: ignore[index]
        if not isinstance(metadata, dict):
            metadata = {}
        return ChatSession(
            id=str(row["id"]),  # type: ignore[index]
            title=str(row["title"]),  # type: ignore[index]
            created_at=int(row["created_at"]),  # type: ignore[index]
            updated_at=int(row["updated_at"]),  # type: ignore[index]
            message_count=int(row["message_count"]),  # type: ignore[index]
            metadata={str(key): value for key, value in metadata.items()},
        )

    @staticmethod
    def _message_from_row(row: object) -> ChatMessage:
        metadata = json.loads(str(row["metadata"]))  # type: ignore[index]
        if not isinstance(metadata, dict):
            metadata = {}
        return ChatMessage(
            id=str(row["id"]),  # type: ignore[index]
            session_id=str(row["session_id"]),  # type: ignore[index]
            role=str(row["role"]),  # type: ignore[index]
            content=str(row["content"]),  # type: ignore[index]
            created_at=int(row["created_at"]),  # type: ignore[index]
            metadata={str(key): value for key, value in metadata.items()},
        )
