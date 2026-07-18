"""Tests for dotenv custom Base URL binding to configured LLM providers."""

from __future__ import annotations

import pytest

from multiscribe_agent.config import ProviderConfig, SystemSettings


def _clear_provider_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove Base URL and key aliases before each isolated Settings assertion."""
    for name in (
        "OPENAI_API_KEY",
        "MULTISCRIBE_OPENAI_API_KEY",
        "OPENAI_API_BASE_URL",
        "MULTISCRIBE_OPENAI_API_BASE_URL",
        "ANTHROPIC_API_KEY",
        "MULTISCRIBE_ANTHROPIC_API_KEY",
        "ANTHROPIC_API_BASE_URL",
        "MULTISCRIBE_ANTHROPIC_API_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_openai_base_url_binds_to_default_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """An OpenAI-compatible relay endpoint reaches the default OpenAI provider only."""
    _clear_provider_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_API_BASE_URL", "https://relay.example.test/v1")

    settings = SystemSettings(_env_file=None)
    openai = next(provider for provider in settings.ai_providers if provider.id == "default-openai")
    anthropic = next(
        provider for provider in settings.ai_providers if provider.id == "default-anthropic"
    )

    assert openai.base_url == "https://relay.example.test/v1"
    assert anthropic.base_url == ""


def test_anthropic_base_url_binds_to_default_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """An Anthropic-compatible relay endpoint reaches the Anthropic provider only."""
    _clear_provider_environment(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_BASE_URL", "https://relay.example.test/anthropic/v1")

    settings = SystemSettings(_env_file=None)
    anthropic = next(
        provider for provider in settings.ai_providers if provider.id == "default-anthropic"
    )

    assert anthropic.base_url == "https://relay.example.test/anthropic/v1"


def test_empty_base_url_keeps_explicit_provider_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty environment value cannot erase an explicitly configured Base URL."""
    _clear_provider_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_API_BASE_URL", "")
    providers = [
        ProviderConfig(
            id="default-openai",
            name="OpenAI",
            type="openai",
            base_url="https://configured.example.test/v1",
            models=["gpt-4o-mini"],
        )
    ]

    settings = SystemSettings(_env_file=None, ai_providers=providers)

    assert settings.ai_providers[0].base_url == "https://configured.example.test/v1"


def test_base_url_and_key_are_independent(monkeypatch: pytest.MonkeyPatch) -> None:
    """A relay endpoint and its API key may be provided independently or together."""
    _clear_provider_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_API_BASE_URL", "https://relay.example.test/v1")

    without_key = SystemSettings(_env_file=None)
    relay_provider = next(
        provider for provider in without_key.ai_providers if provider.id == "default-openai"
    )
    assert relay_provider.base_url == "https://relay.example.test/v1"
    assert relay_provider.api_key == ""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with_key = SystemSettings(_env_file=None)
    keyed_provider = next(
        provider for provider in with_key.ai_providers if provider.id == "default-openai"
    )
    assert keyed_provider.base_url == "https://relay.example.test/v1"
    assert keyed_provider.api_key == "test-key"
