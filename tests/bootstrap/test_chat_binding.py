"""Tests that ServiceContext.init() late-binds the chat executor to ChatService."""

from __future__ import annotations

from typing import Any

import pytest

from multiscribe_agent.bootstrap import (
    DEFAULT_CHAT_AGENT_ID,
    ServiceContext,
    _ChatAgentRunner,
)
from multiscribe_agent.config import SystemSettings
from multiscribe_agent.services.chat_service import ChatService
from tests.db import get_test_database_url


def _runner(context: ServiceContext) -> object:
    """Return the chat runner attribute (single source for SLF001)."""
    return context.chat_service._agent_runner


def _agent_def(context: ServiceContext) -> object:
    """Return the chat agent definition attribute (single source for SLF001)."""
    return context.chat_service._agent_def


async def _build_context() -> ServiceContext:
    """Build a fresh ServiceContext backed by the PostgreSQL test database."""
    settings = SystemSettings(_env_file=None, database_url=get_test_database_url())
    context = ServiceContext(settings)
    await context.init()
    return context


@pytest.mark.asyncio
async def test_init_binds_chat_runner_and_default_definition() -> None:
    """init() must wire the chat executor to a default-chat-agent definition."""
    context = await _build_context()
    try:
        assert isinstance(context.chat_service, ChatService)
        assert isinstance(_runner(context), _ChatAgentRunner)
        agent_def = _agent_def(context)
        assert agent_def is not None
        assert agent_def.id == DEFAULT_CHAT_AGENT_ID
        raw = await context.entities.get("agents", DEFAULT_CHAT_AGENT_ID)  # type: ignore[union-attr]
        assert raw is not None
        assert raw["id"] == DEFAULT_CHAT_AGENT_ID
    finally:
        await context.close()


@pytest.mark.asyncio
async def test_init_is_idempotent_for_chat_agent() -> None:
    """Re-running init() must not duplicate the default-chat-agent row."""
    context = await _build_context()
    try:
        first_raw: dict[str, Any] | None = await context.entities.get(  # type: ignore[union-attr]
            "agents", DEFAULT_CHAT_AGENT_ID
        )
        first_runner = _runner(context)
        await context.init()
        second_raw: dict[str, Any] | None = await context.entities.get(  # type: ignore[union-attr]
            "agents", DEFAULT_CHAT_AGENT_ID
        )
        assert first_raw is not None
        assert second_raw is not None
        assert first_raw == second_raw
        assert _runner(context) is first_runner
    finally:
        await context.close()
