"""Tests for the ChatService orchestration and async preference extraction."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from multiscribe_agent.infra.db import init_db
from multiscribe_agent.memory.chat_sessions import ChatSessionRepository
from multiscribe_agent.memory.preference_store import PreferenceStore, UserPreferences
from multiscribe_agent.memory.repositories.memory_categories import MemoryCategoryRepository
from multiscribe_agent.services.chat_service import _UNBOUND_PLACEHOLDER, ChatService


@dataclass
class ScriptedAgent:
    """Return a deterministic assistant message for every call."""

    reply: str

    async def run(self, agent_def: Any, user_input: str) -> str:
        return self.reply


class ScriptedExtractor:
    """Capture merge calls and return a configured delta."""

    def __init__(self, delta: dict[str, object] | None) -> None:
        self._delta = delta or {}
        self.calls = 0
        self.last_messages: list[Any] = []

    async def extract_from_conversation(self, messages: list[Any]) -> dict[str, object]:
        self.calls += 1
        self.last_messages = list(messages)
        return dict(self._delta)

    def merge_into(self, preferences: UserPreferences, delta: dict[str, object]) -> UserPreferences:
        merged_tags = list(
            dict.fromkeys([*preferences.preferred_tags, *delta.get("preferred_tags", [])])
        )
        return UserPreferences(
            preferred_tags=merged_tags,
            block_sources=list(preferences.block_sources),
            push_time=preferences.push_time,
            importance_threshold=preferences.importance_threshold,
            blocked_topics=list(preferences.blocked_topics),
        )


def _no_provider() -> None:
    """Placeholder to mirror the real PreferenceExtractor construction signature."""
    return None


async def _build_service(
    delta: dict[str, object] | None,
    reply: str = "ack",
) -> tuple[ChatService, PreferenceStore, Any, Any]:
    db = await init_db(":memory:")
    category_repo = MemoryCategoryRepository(db)
    store = PreferenceStore(category_repo)
    sessions = ChatSessionRepository(db)
    extractor = ScriptedExtractor(delta)  # type: ignore[arg-type]
    agent_def = type("FakeDef", (), {})()  # type: ignore[arg-type]
    service = ChatService(sessions, store, extractor, ScriptedAgent(reply), agent_def)  # type: ignore[arg-type]
    return service, store, db, sessions


@pytest.mark.asyncio
async def test_send_message_autotitles_blank_session() -> None:
    """A blank-title session gets its first message as the displayed title."""
    service, _, db, _ = await _build_service(delta=None)
    try:
        session = await service.create_session("")  # type: ignore[arg-type]
        await service.send_message(session.id, "看看 RAG 实战要点")
        updated = await service.list_sessions(limit=5)
        target = next(item for item in updated if item.id == session.id)
        assert target.title == "看看 RAG 实战要点"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_send_message_preserves_user_supplied_title() -> None:
    """A custom title is not overwritten by the first message."""
    service, _, db, _ = await _build_service(delta=None)
    try:
        session = await service.create_session("我的主题")
        await service.send_message(session.id, "看看 RAG 实战要点")
        updated = await service.list_sessions(limit=5)
        target = next(item for item in updated if item.id == session.id)
        assert target.title == "我的主题"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_send_message_truncates_long_autotitle() -> None:
    """Long first messages collapse to a 24-character preview with an ellipsis."""
    service, _, db, _ = await _build_service(delta=None)
    try:
        session = await service.create_session("")
        await service.send_message(
            session.id,
            "帮我深入研究一下 Agent 框架在企业级落地时遇到的工程难点",
        )
        updated = await service.list_sessions(limit=5)
        target = next(item for item in updated if item.id == session.id)
        assert target.title.endswith("…")
        assert len(target.title) <= 25
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_send_message_persists_user_and_assistant_turns() -> None:
    """A user turn triggers one persisted assistant reply."""
    service, _, db, _ = await _build_service(delta=None)
    try:
        session = await service.create_session("first")
        reply = await service.send_message(session.id, "  帮我看看  ")
        assert reply is not None
        assert reply.role == "assistant"
        assert reply.content == "ack"
        messages = await service.list_messages(session.id)
        assert [message.role for message in messages] == ["user", "assistant"]
        assert messages[0].content == "帮我看看"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_send_message_missing_session_returns_none() -> None:
    """Sending a message to a deleted session reports None instead of raising."""
    service, _, db, _ = await _build_service(delta=None)
    try:
        result = await service.send_message("does-not-exist", "hi")
        assert result is None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_send_message_defer_preference_extraction_runs_async() -> None:
    """Successful extraction merges the delta into stored preferences asynchronously."""
    service, store, db, _ = await _build_service(delta={"preferred_tags": ["RAG", "agent"]})
    try:
        session = await service.create_session()
        await service.send_message(session.id, "看看 RAG 资料")
        # The async task is scheduled on the running loop; wait briefly for it to flush.
        for _ in range(20):
            await asyncio.sleep(0.05)
            prefs = await store.load()
            if "RAG" in prefs.preferred_tags:
                break
        prefs = await store.load()
        assert "RAG" in prefs.preferred_tags
        assert "agent" in prefs.preferred_tags
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_delete_session_removes_messages() -> None:
    """delete_session cascades to remove the message rows for that session."""
    service, _, db, _ = await _build_service(delta=None)
    try:
        session = await service.create_session()
        await service.send_message(session.id, "first")
        await service.send_message(session.id, "second")
        assert await service.delete_session(session.id) is True
        assert await service.list_sessions() == []
        assert await service.list_messages(session.id) == []
    finally:
        await db.close()


async def _build_unbound_service() -> tuple[ChatService, Any]:
    """Build a ChatService that has not yet received an agent binding."""
    db = await init_db(":memory:")
    category_repo = MemoryCategoryRepository(db)
    store = PreferenceStore(category_repo)
    sessions = ChatSessionRepository(db)
    extractor = ScriptedExtractor(None)  # type: ignore[arg-type]
    service = ChatService(sessions, store, extractor)
    return service, db


@pytest.mark.asyncio
async def test_send_message_returns_placeholder_when_unbound() -> None:
    """Without bind_agent the chat reply is the documented placeholder string."""
    service, db = await _build_unbound_service()
    try:
        session = await service.create_session()
        reply = await service.send_message(session.id, "  你好  ")
        assert reply is not None
        assert reply.role == "assistant"
        assert reply.content == _UNBOUND_PLACEHOLDER
        messages = await service.list_messages(session.id)
        assert [message.role for message in messages] == ["user", "assistant"]
        assert messages[0].content == "你好"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_send_message_invokes_bound_runner_and_persists_reply() -> None:
    """After bind_agent every send_message call drives the configured runner once."""
    db = await init_db(":memory:")
    category_repo = MemoryCategoryRepository(db)
    store = PreferenceStore(category_repo)
    sessions = ChatSessionRepository(db)
    extractor = ScriptedExtractor(None)  # type: ignore[arg-type]
    agent_def = type("FakeDef", (), {"id": "agent-x"})()
    scripted = ScriptedAgent("answer-from-agent")
    service = ChatService(sessions, store, extractor, scripted, agent_def)  # type: ignore[arg-type]
    try:
        session = await service.create_session("bound")
        reply = await service.send_message(session.id, "hi")
        assert reply is not None
        assert reply.content == "answer-from-agent"
        messages = await service.list_messages(session.id)
        assert [message.role for message in messages] == ["user", "assistant"]
        assert messages[1].content == "answer-from-agent"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_bind_agent_overrides_constructor_default() -> None:
    """bind_agent switches the runner used by later send_message calls."""
    db = await init_db(":memory:")
    category_repo = MemoryCategoryRepository(db)
    store = PreferenceStore(category_repo)
    sessions = ChatSessionRepository(db)
    extractor = ScriptedExtractor(None)  # type: ignore[arg-type]
    service = ChatService(sessions, store, extractor)
    original = ScriptedAgent("placeholder")
    replacement = ScriptedAgent("rebound-answer")
    new_def = type("FakeDef", (), {"id": "rebound"})()
    service.bind_agent(original, type("FakeDef", (), {"id": "first"})())  # type: ignore[arg-type]
    service.bind_agent(replacement, new_def)  # type: ignore[arg-type]
    try:
        session = await service.create_session()
        reply = await service.send_message(session.id, "ping")
        assert reply is not None
        assert reply.content == "rebound-answer"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_send_message_defer_preference_extraction_returns_after_bind() -> None:
    """Bound send_message still schedules the async extraction task without raising."""
    db = await init_db(":memory:")
    category_repo = MemoryCategoryRepository(db)
    store = PreferenceStore(category_repo)
    sessions = ChatSessionRepository(db)
    extractor = ScriptedExtractor({"preferred_tags": ["RAG"]})  # type: ignore[arg-type]
    agent_def = type("FakeDef", (), {})()
    service = ChatService(
        sessions,
        store,
        extractor,
        ScriptedAgent("ack"),
        agent_def,  # type: ignore[arg-type]
    )
    try:
        session = await service.create_session()
        reply = await service.send_message(session.id, "看看 RAG")
        assert reply is not None
        assert reply.content == "ack"
        for _ in range(20):
            await asyncio.sleep(0.05)
            prefs = await store.load()
            if "RAG" in prefs.preferred_tags:
                break
        prefs = await store.load()
        assert "RAG" in prefs.preferred_tags
    finally:
        await db.close()
