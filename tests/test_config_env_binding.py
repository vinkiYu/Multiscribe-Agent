"""Tests for the MVP dotenv-to-runtime configuration bridge."""

from __future__ import annotations

import pytest

from multiscribe_agent.bootstrap import DEFAULT_CURATION_AGENT_ID, ServiceContext
from multiscribe_agent.config import ProviderConfig, SystemSettings


def _clear_mvp_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests exercise only the environment values they explicitly provide."""
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "FEISHU_WEBHOOK",
        "FEISHU_SECRET",
        "WECOM_WEBHOOK",
        "DEFAULT_CURATION_PROVIDER_ID",
        "DEFAULT_CURATION_MODEL",
        "DEFAULT_CURATION_TEMPERATURE",
        "DEFAULT_DIGEST_TARGETS",
        "DEFAULT_DIGEST_TOP_N",
        "DEFAULT_DIGEST_FETCH_DAYS",
        "DEFAULT_DIGEST_ADAPTER_IDS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_openai_key_binds_to_default_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """A flat dotenv key reaches the selected structured provider configuration."""
    _clear_mvp_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = SystemSettings(_env_file=None)
    provider = next(item for item in settings.ai_providers if item.id == "default-openai")

    assert provider.api_key == "sk-test"


def test_webhooks_enable_and_configure_mvp_publishers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured delivery endpoints become enabled publisher options without logging secrets."""
    _clear_mvp_environment(monkeypatch)
    monkeypatch.setenv("FEISHU_WEBHOOK", "https://feishu.example.test/hook")
    monkeypatch.setenv("FEISHU_SECRET", "test-secret")
    monkeypatch.setenv("WECOM_WEBHOOK", "https://wecom.example.test/hook")

    settings = SystemSettings(_env_file=None)
    publishers = {publisher.id: publisher for publisher in settings.publishers}

    assert publishers["feishu_bot"].enabled is True
    assert publishers["feishu_bot"].config == {
        "webhook": "https://feishu.example.test/hook",
        "secret": "test-secret",
    }
    assert publishers["wecom_bot"].enabled is True
    assert publishers["wecom_bot"].config == {"webhook": "https://wecom.example.test/hook"}


def test_empty_environment_key_keeps_explicit_provider_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty dotenv value cannot erase a configured provider credential."""
    _clear_mvp_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    providers = [
        ProviderConfig(
            id="default-openai",
            name="OpenAI",
            type="openai",
            api_key="configured-key",
            models=["gpt-4o-mini"],
        )
    ]

    settings = SystemSettings(_env_file=None, ai_providers=providers)

    assert settings.ai_providers[0].api_key == "configured-key"


def test_default_digest_settings_have_mvp_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default daily-digest choices are usable without custom configuration."""
    _clear_mvp_environment(monkeypatch)

    settings = SystemSettings(_env_file=None)

    assert settings.default_curation_provider_id == "default-openai"
    assert settings.default_curation_model == "gpt-4o-mini"
    assert settings.default_curation_temperature == 0.3
    assert settings.default_digest_targets == ["feishu_bot", "wecom_bot"]
    assert settings.default_digest_top_n == 5
    assert settings.default_digest_fetch_days == 2
    assert settings.default_digest_adapter_ids == ["rss-adapter"]


@pytest.mark.asyncio
async def test_bootstrap_persists_default_curation_agent(tmp_path) -> None:
    """A new service database receives the default curator exactly once at startup."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "mvp.sqlite"))
    context = ServiceContext(settings)
    await context.init()
    try:
        assert context.entities is not None
        stored = await context.entities.get("agents", DEFAULT_CURATION_AGENT_ID)
        assert stored is not None
        assert stored["provider_id"] == "default-openai"
        assert stored["model"] == "gpt-4o-mini"
        assert stored["temperature"] == 0.3
    finally:
        await context.close()
