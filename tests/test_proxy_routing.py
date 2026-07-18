"""Tests for dotenv proxy aliases and bootstrap-to-provider proxy routing."""

from __future__ import annotations

import pytest

from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import ProviderConfig, SystemSettings
from multiscribe_agent.domain.models import AgentDefinition


def _clear_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove both supported proxy aliases before each settings assertion."""
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("MULTISCRIBE_HTTP_PROXY", raising=False)


def _agent(agent_id: str = "agent") -> AgentDefinition:
    """Build a stored-agent-compatible definition using the OpenAI default provider."""
    return AgentDefinition(
        id=agent_id,
        name=agent_id,
        description="proxy routing test agent",
        system_prompt="Return JSON only.",
        provider_id="default-openai",
        model="gpt-4o-mini",
    )


def test_proxy_aliases_support_unprefixed_prefixed_and_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both documented dotenv names populate one Settings field, while omission stays empty."""
    _clear_proxy_environment(monkeypatch)
    assert SystemSettings(_env_file=None).http_proxy == ""

    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example.test:8080")
    assert SystemSettings(_env_file=None).http_proxy == "http://proxy.example.test:8080"

    monkeypatch.delenv("HTTP_PROXY")
    monkeypatch.setenv("MULTISCRIBE_HTTP_PROXY", "http://proxy.example.test:7890")
    assert SystemSettings(_env_file=None).http_proxy == "http://proxy.example.test:7890"


def test_context_passes_proxy_to_each_provider_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every selected AgentDefinition receives the configured global proxy consistently."""
    captured_proxies: list[str | None] = []

    def fake_create_provider(
        provider: ProviderConfig,
        *,
        model: str | None = None,
        temperature: float | None = None,
        proxy: str | None = None,
    ) -> object:
        del provider, model, temperature
        captured_proxies.append(proxy)
        return object()

    monkeypatch.setattr("multiscribe_agent.bootstrap.create_provider", fake_create_provider)
    settings = SystemSettings(_env_file=None)
    settings.http_proxy = "http://proxy.example.test:7890"
    context = ServiceContext(settings)

    context._provider_for_agent(_agent("one"))
    context._provider_for_agent(_agent("two"))

    assert captured_proxies == ["http://proxy.example.test:7890"] * 2


def test_context_passes_none_for_empty_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty Settings value becomes None instead of an invalid empty proxy URL."""
    captured_proxies: list[str | None] = []

    def fake_create_provider(
        provider: ProviderConfig,
        *,
        model: str | None = None,
        temperature: float | None = None,
        proxy: str | None = None,
    ) -> object:
        del provider, model, temperature
        captured_proxies.append(proxy)
        return object()

    monkeypatch.setattr("multiscribe_agent.bootstrap.create_provider", fake_create_provider)
    context = ServiceContext(SystemSettings(_env_file=None))

    context._provider_for_agent(_agent())

    assert captured_proxies == [None]
