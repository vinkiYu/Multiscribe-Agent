"""Tests that ServiceContext.init() late-binds the chat executor to ChatService."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from multiscribe_agent.bootstrap import (
    DEFAULT_CHAT_AGENT_ID,
    ServiceContext,
    _ChatAgentRunner,
)
from multiscribe_agent.config import SystemSettings
from multiscribe_agent.services.chat_service import ChatService


def _runner(context: ServiceContext) -> object:
    """Return the chat runner attribute (single source for SLF001)."""
    return context.chat_service._agent_runner


def _agent_def(context: ServiceContext) -> object:
    """Return the chat agent definition attribute (single source for SLF001)."""
    return context.chat_service._agent_def


async def _build_context() -> tuple[ServiceContext, Path]:
    """Build a fresh ServiceContext backed by a per-test SQLite database."""
    tmp_root = Path(".pytest-tmp") / "p59-chat-binding"
    tmp_root.mkdir(parents=True, exist_ok=True)
    db_path = tmp_root / "chat_binding.sqlite"
    settings = SystemSettings(_env_file=None, db_path=str(db_path))
    context = ServiceContext(settings)
    await context.init()
    return context, db_path


@pytest.mark.asyncio
async def test_init_binds_chat_runner_and_default_definition() -> None:
    """init() must wire the chat executor to a default-chat-agent definition."""
    context, db_path = await _build_context()
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
        db_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_init_is_idempotent_for_chat_agent() -> None:
    """Re-running init() must not duplicate the default-chat-agent row."""
    context, db_path = await _build_context()
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
        db_path.unlink(missing_ok=True)
