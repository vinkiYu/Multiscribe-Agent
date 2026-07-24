"""Model-specific context-window configuration compatibility tests."""

import pytest
from pydantic import ValidationError

from multiscribe_agent.config import ProviderConfig
from multiscribe_agent.domain.models import AgentDefinition


def test_provider_model_limits_use_compatible_defaults_and_overrides() -> None:
    config = ProviderConfig(
        id="proxy",
        name="Proxy",
        type="openai",
        models=["small", "default"],
        context_window_tokens={"small": 8_192},
        default_output_tokens={"small": 512},
    )

    assert config.model_context_window("small") == 8_192
    assert config.model_output_tokens("small") == 512
    assert config.model_context_window("default") == 128_000
    assert config.model_output_tokens("default") == 4_096


def test_model_limits_and_agent_output_limit_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            id="invalid",
            name="Invalid",
            type="openai",
            context_window_tokens={"model": 0},
        )

    with pytest.raises(ValidationError):
        AgentDefinition(
            id="agent",
            name="Agent",
            description="test",
            system_prompt="test",
            provider_id="provider",
            model="model",
            max_output_tokens=0,
        )
