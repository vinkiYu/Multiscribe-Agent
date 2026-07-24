"""Tests for default, environment, and persistent settings layers."""

from multiscribe_agent.config import ConfigService, ProviderConfig, SystemSettings, get_settings


def test_get_settings_defaults(monkeypatch) -> None:
    """Default settings contain the expected baseline values and plugins."""
    monkeypatch.delenv("MULTISCRIBE_LOG_LEVEL", raising=False)
    monkeypatch.delenv("MULTISCRIBE_DB_PATH", raising=False)

    settings = get_settings()

    assert settings.db_path == "data/database.sqlite"
    assert settings.log_level == "INFO"
    assert settings.selection_fetch_days == 2
    assert settings.selection_query_field == "ingestion_date"
    assert len(settings.ai_providers) == 4
    assert len(settings.adapters) == 4
    assert len(settings.publishers) == 5
    assert len(settings.storages) == 2


def test_default_plugin_identifiers() -> None:
    """Default plugin identifiers preserve original and MVP destinations."""
    settings = SystemSettings(_env_file=None)

    assert {provider.type for provider in settings.ai_providers} == {
        "openai",
        "anthropic",
        "google",
        "ollama",
    }
    assert {adapter.id for adapter in settings.adapters} == {
        "github-trending",
        "follow-api",
        "ai-search",
        "rss-adapter",
    }
    assert {publisher.id for publisher in settings.publishers} == {
        "feishu_bot",
        "wecom_bot",
        "github",
        "wechat",
        "rss",
    }
    assert {storage.id for storage in settings.storages} == {"r2", "github_storage"}


def test_environment_overrides_settings(monkeypatch) -> None:
    """MULTISCRIBE-prefixed process variables override defaults."""
    monkeypatch.setenv("MULTISCRIBE_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("MULTISCRIBE_DB_PATH", "data/test.sqlite")
    monkeypatch.setenv("MULTISCRIBE_SELECTION_FETCH_DAYS", "7")

    settings = get_settings()

    assert settings.log_level == "DEBUG"
    assert settings.db_path == "data/test.sqlite"
    assert settings.selection_fetch_days == 7


def test_default_collections_are_isolated() -> None:
    """Settings instances do not share mutable default collections."""
    first = SystemSettings(_env_file=None)
    second = SystemSettings(_env_file=None)

    first.closed_plugins.append("rss")

    assert second.closed_plugins == []


async def test_config_service_applies_persistent_overrides(monkeypatch) -> None:
    """The third settings layer overrides values loaded from the environment."""

    class OverrideConfigService(ConfigService):
        async def load_overrides(self) -> dict[str, object]:
            return {"log_level": "WARNING", "selection_fetch_days": 5}

    monkeypatch.setenv("MULTISCRIBE_LOG_LEVEL", "DEBUG")

    settings = await OverrideConfigService().get_settings_with_overrides()

    assert settings.log_level == "WARNING"
    assert settings.selection_fetch_days == 5


def test_default_providers_have_known_model_windows_and_output_limits() -> None:
    """Bundled models use explicit production limits instead of compatibility fallbacks."""
    settings = SystemSettings(_env_file=None)
    openai = next(provider for provider in settings.ai_providers if provider.type == "openai")
    anthropic = next(provider for provider in settings.ai_providers if provider.type == "anthropic")
    ollama = next(provider for provider in settings.ai_providers if provider.type == "ollama")

    assert openai.context_window_tokens["gpt-4o"] == 128_000
    assert openai.default_output_tokens["gpt-4o"] == 16_384
    assert anthropic.context_window_tokens["claude-sonnet-4-5"] == 200_000
    assert ollama.context_window_tokens["qwen2.5"] == 32_768


def test_environment_overrides_provider_model_limits(monkeypatch) -> None:
    """JSON environment mappings override matching configured model limits."""
    monkeypatch.setenv("PROVIDER_CONTEXT_WINDOWS", '{"gpt-4o": 64000}')
    monkeypatch.setenv("PROVIDER_OUTPUT_TOKENS", '{"gpt-4o": 2048}')

    settings = SystemSettings(_env_file=None)
    openai = next(provider for provider in settings.ai_providers if provider.type == "openai")

    assert openai.context_window_tokens["gpt-4o"] == 64_000
    assert openai.default_output_tokens["gpt-4o"] == 2_048


def test_environment_overrides_custom_configured_model(monkeypatch) -> None:
    """Unknown relay models can declare their real window without a code change."""
    monkeypatch.setenv("PROVIDER_CONTEXT_WINDOWS", '{"custom-model": 32000}')
    settings = SystemSettings(
        _env_file=None,
        ai_providers=[
            ProviderConfig(
                id="relay",
                name="Relay",
                type="openai",
                models=["custom-model"],
            )
        ],
    )

    assert settings.ai_providers[0].context_window_tokens["custom-model"] == 32_000
