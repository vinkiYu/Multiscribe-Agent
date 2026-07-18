"""Regression coverage for relay-specific model names outside the default catalog."""

from __future__ import annotations

import pytest

from multiscribe_agent.config import ProviderConfig
from multiscribe_agent.llm.provider import create_provider
from multiscribe_agent.llm.providers.openai import OpenAIProvider


def test_custom_model_name_is_forwarded_outside_provider_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit relay model name bypasses the documented model catalog."""
    captured_models: list[str] = []

    def fake_chat_openai(*, model: str, **_: object) -> object:
        captured_models.append(model)
        return object()

    monkeypatch.setattr("multiscribe_agent.llm.providers.openai.ChatOpenAI", fake_chat_openai)
    config = ProviderConfig(
        id="relay-openai",
        name="Relay OpenAI",
        type="openai",
        api_key="test-key",
        models=["gpt-4o-mini"],
    )

    provider = create_provider(config, model="gpt-5.2")

    assert "gpt-5.2" not in config.models
    assert isinstance(provider, OpenAIProvider)
    assert captured_models == ["gpt-5.2"]
