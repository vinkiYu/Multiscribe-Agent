from __future__ import annotations

import pytest

from multiscribe_agent.agents.pipelines.daily_digest import OVERVIEW_AGENT_ID
from multiscribe_agent.bootstrap import DEFAULT_OVERVIEW_AGENT_PROMPT, ServiceContext
from multiscribe_agent.config import SystemSettings


def _settings(
    model: str = "gpt-4o-mini",
    provider_id: str = "default-openai",
    temperature: float = 0.3,
) -> SystemSettings:
    """Build settings for the overview bootstrap tests."""
    cfg = SystemSettings(_env_file=None)
    cfg.default_curation_provider_id = provider_id
    cfg.default_curation_model = model
    cfg.default_curation_temperature = temperature
    return cfg


def _stored_overview_agent(
    model: str = "gpt-4o-mini",
    provider_id: str = "default-openai",
    temperature: float = 0.3,
    system_prompt: str = DEFAULT_OVERVIEW_AGENT_PROMPT,
) -> dict[str, object]:
    """Return a persisted AgentDefinition-shaped overview entity."""
    return {
        "id": OVERVIEW_AGENT_ID,
        "name": "Daily Digest Overview Agent",
        "description": "Writes the natural-language overview for the daily digest.",
        "system_prompt": system_prompt,
        "provider_id": provider_id,
        "model": model,
        "temperature": temperature,
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
        self._store: dict[str, dict[str, object]] = {}

    async def get(self, _kind: str, id: str) -> dict[str, object] | None:
        return self._store.get(id)

    async def save(self, _kind: str, id: str, data: dict[str, object]) -> None:
        self._store[id] = data


@pytest.mark.asyncio
async def test_bootstrap_creates_dedicated_overview_agent() -> None:
    """Bootstrap creates a natural-language overview declaration when absent."""
    entities = _FakeEntities()
    context = ServiceContext(_settings(model="gpt-5.4-mini", provider_id="proxy"))

    await context._bootstrap_default_overview_agent(entities)  # type: ignore[arg-type]

    agent = entities._store[OVERVIEW_AGENT_ID]
    assert agent["id"] == OVERVIEW_AGENT_ID
    assert agent["name"] == "Daily Digest Overview Agent"
    assert agent["description"] == "Writes the natural-language overview for the daily digest."
    assert agent["provider_id"] == "proxy"
    assert agent["model"] == "gpt-5.4-mini"
    assert agent["temperature"] == 0.3
    assert agent["system_prompt"] == DEFAULT_OVERVIEW_AGENT_PROMPT
    assert "JSON array" not in str(agent["system_prompt"])


@pytest.mark.asyncio
async def test_bootstrap_overview_agent_is_idempotent() -> None:
    """A matching overview declaration must not be rewritten."""
    entities = _FakeEntities()
    entities._store[OVERVIEW_AGENT_ID] = _stored_overview_agent()
    context = ServiceContext(_settings())
    before = entities._store[OVERVIEW_AGENT_ID]

    await context._bootstrap_default_overview_agent(entities)  # type: ignore[arg-type]

    assert entities._store[OVERVIEW_AGENT_ID] is before


@pytest.mark.asyncio
async def test_bootstrap_overview_agent_updates_configuration_drift() -> None:
    """Provider, model, temperature, and prompt drift are synchronized on bootstrap."""
    entities = _FakeEntities()
    entities._store[OVERVIEW_AGENT_ID] = _stored_overview_agent(
        model="old-model",
        provider_id="old-provider",
        temperature=0.9,
        system_prompt="legacy overview prompt",
    )
    context = ServiceContext(
        _settings(model="new-model", provider_id="new-provider", temperature=0.2)
    )

    await context._bootstrap_default_overview_agent(entities)  # type: ignore[arg-type]

    agent = entities._store[OVERVIEW_AGENT_ID]
    assert agent["provider_id"] == "new-provider"
    assert agent["model"] == "new-model"
    assert agent["temperature"] == 0.2
    assert agent["system_prompt"] == DEFAULT_OVERVIEW_AGENT_PROMPT
