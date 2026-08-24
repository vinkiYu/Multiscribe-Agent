"""Repository-level tests for chat_sessions and chat_messages persistence."""

from __future__ import annotations

import pytest

from multiscribe_agent.infra.db import init_db
from multiscribe_agent.memory.chat_sessions import ChatSessionRepository


@pytest.mark.asyncio
async def test_create_get_list_delete_session_lifecycle() -> None:
    """Create, list, and delete a chat session; cascade removes its messages."""
    db = await init_db(":memory:")
    try:
        repo = ChatSessionRepository(db)
        session = await repo.create_session("AI 笔记")
        assert session.title == "AI 笔记"
        assert session.message_count == 0

        listed = await repo.list_sessions()
        assert [item.id for item in listed] == [session.id]

        loaded = await repo.get_session(session.id)
        assert loaded is not None
        assert loaded.title == "AI 笔记"

        assert await repo.delete_session(session.id) is True
        assert await repo.get_session(session.id) is None
        assert await repo.list_sessions() == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_append_message_increments_count_and_updates_timestamp() -> None:
    """Adding a user message bumps message_count and the session updated_at timer."""
    db = await init_db(":memory:")
    try:
        repo = ChatSessionRepository(db)
        session = await repo.create_session()
        first = await repo.append_message(session.id, "user", "你好")
        assert first is not None
        assert first.role == "user"
        assert first.content == "你好"

        second = await repo.append_message(session.id, "assistant", "你好，我能帮什么？")
        assert second is not None
        loaded = await repo.get_session(session.id)
        assert loaded is not None
        assert loaded.message_count == 2
        assert loaded.updated_at >= first.created_at
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_append_message_returns_none_for_missing_session() -> None:
    """append_message against a non-existent session returns None instead of raising."""
    db = await init_db(":memory:")
    try:
        repo = ChatSessionRepository(db)
        result = await repo.append_message("missing-id", "user", "hi")
        assert result is None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_append_message_rejects_invalid_role_or_empty_content() -> None:
    """Bad role and empty content are rejected before hitting storage."""
    db = await init_db(":memory:")
    try:
        repo = ChatSessionRepository(db)
        session = await repo.create_session()
        with pytest.raises(ValueError, match="role"):
            await repo.append_message(session.id, "tool", "x")
        with pytest.raises(ValueError, match="content"):
            await repo.append_message(session.id, "user", "   ")
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_list_messages_returns_chronological_order() -> None:
    """Messages for a session are returned in ascending created_at order."""
    db = await init_db(":memory:")
    try:
        repo = ChatSessionRepository(db)
        session = await repo.create_session()
        await repo.append_message(session.id, "user", "1")
        await repo.append_message(session.id, "assistant", "2")
        await repo.append_message(session.id, "user", "3")
        messages = await repo.list_messages(session.id)
        assert [message.content for message in messages] == ["1", "2", "3"]
        assert [message.role for message in messages] == ["user", "assistant", "user"]
    finally:
        await db.close()
