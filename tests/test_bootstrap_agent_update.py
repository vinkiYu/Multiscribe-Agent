"""Tests for bootstrap agent update / idempotent behavior."""

from __future__ import annotations

import pytest

from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings

DEFAULT_AGENT_ID = "default-curation-agent"


def _settings(model: str = "gpt-4o-mini", provider_id: str = "default-openai") -> SystemSettings:
    """Build settings with a specific model for the default curation agent."""
    cfg = SystemSettings(_env_file=None)
    cfg.default_curation_provider_id = provider_id
    cfg.default_curation_model = model
    cfg.default_curation_temperature = 0.3
    return cfg


def _stored_agent(model: str = "gpt-4o-mini", provider_id: str = "default-openai") -> dict:
    return {
        "id": DEFAULT_AGENT_ID,
        "name": "Default Curation Agent",
        "description": "MVP default curation agent created by bootstrap.",
        "system_prompt": "You are a news curation assistant.",
        "provider_id": provider_id,
        "model": model,
        "temperature": 0.3,
        "tool_ids": [],
        "skill_ids": [],
        "mcp_server_ids": [],
        "streaming": False,
        "is_hidden": False,
        "category": None,
    }


class _FakeEntities:
    """In-memory entity store for isolated bootstrap tests."""

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    async def get(self, _kind: str, id: str) -> dict | None:
        return self._store.get(id)

    async def save(self, _kind: str, id: str, data: dict) -> None:
        self._store[id] = data


@pytest.mark.asyncio
async def test_bootstrap_creates_agent_when_absent() -> None:
    """Bootstrap must create the default curation agent if it does not exist."""
    entities = _FakeEntities()
    settings = _settings(model="gpt-5.4-mini")
    context = ServiceContext(settings)
    context._initialized = True  # bypass full init

    await context._bootstrap_default_curation_agent(entities)

    assert DEFAULT_AGENT_ID in entities._store
    agent = entities._store[DEFAULT_AGENT_ID]
    assert agent["model"] == "gpt-5.4-mini"
    assert agent["provider_id"] == "default-openai"


@pytest.mark.asyncio
async def test_bootstrap_updates_agent_when_settings_have_changed() -> None:
    """When the stored model differs from settings, bootstrap must overwrite it."""
    entities = _FakeEntities()
    entities._store[DEFAULT_AGENT_ID] = _stored_agent(model="gpt-4o-mini")

    settings = _settings(model="gpt-5.4-mini")
    context = ServiceContext(settings)
    context._initialized = True

    await context._bootstrap_default_curation_agent(entities)

    agent = entities._store[DEFAULT_AGENT_ID]
    assert agent["model"] == "gpt-5.4-mini", "stale model should be updated"


@pytest.mark.asyncio
async def test_bootstrap_leaves_agent_unchanged_when_idempotent() -> None:
    """When stored agent matches settings, bootstrap must not rewrite it."""
    entities = _FakeEntities()
    entities._store[DEFAULT_AGENT_ID] = _stored_agent(model="gpt-5.4-mini")

    settings = _settings(model="gpt-5.4-mini")
    context = ServiceContext(settings)
    context._initialized = True

    before = entities._store[DEFAULT_AGENT_ID]
    await context._bootstrap_default_curation_agent(entities)
    after = entities._store[DEFAULT_AGENT_ID]

    assert before is after, "identical agent should not be rewritten"
