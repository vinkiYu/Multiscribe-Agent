"""Application settings and layered configuration access."""

from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from multiscribe_agent.core.errors import ConfigError
from multiscribe_agent.domain.ports import KvRepository as KvRepositoryPort


class ProviderConfig(BaseModel):
    """Configuration for one AI provider endpoint.

    A single endpoint (one api_key + base_url) may serve multiple models; ``models``
    is the list of model ids this endpoint exposes (for validation / UI selection).
    The concrete model used per call is supplied by ``AgentDefinition.model`` and
    injected into the provider at construction time.
    """

    model_config = ConfigDict(frozen=False)

    id: str
    name: str
    type: Literal["openai", "anthropic", "google", "ollama"]
    api_key: str = ""
    base_url: str = ""
    use_proxy: bool = False
    models: list[str] = Field(default_factory=list)


class AdapterConfig(BaseModel):
    """Configuration for one content adapter."""

    model_config = ConfigDict(frozen=False)

    id: str
    type: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class PublisherConfig(BaseModel):
    """Configuration for one content publisher."""

    model_config = ConfigDict(frozen=False)

    id: str
    type: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class StorageConfig(BaseModel):
    """Configuration for one asset storage provider."""

    model_config = ConfigDict(frozen=False)

    id: str
    type: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


def _default_ai_providers() -> list[ProviderConfig]:
    return [
        ProviderConfig(
            id="default-google",
            name="Google Gemini",
            type="google",
            models=["gemini-2.0-flash", "gemini-2.5-pro", "gemini-1.5-pro"],
        ),
        ProviderConfig(
            id="default-anthropic",
            name="Anthropic",
            type="anthropic",
            models=["claude-sonnet-4-5", "claude-opus-4-1", "claude-3-5-haiku-latest"],
        ),
        ProviderConfig(
            id="default-openai",
            name="OpenAI",
            type="openai",
            models=["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o3-mini"],
        ),
        ProviderConfig(
            id="default-ollama",
            name="Ollama",
            type="ollama",
            base_url="http://localhost:11434",
            models=["llama3.1", "qwen2.5", "deepseek-r1"],
        ),
    ]


def _default_adapters() -> list[AdapterConfig]:
    return [
        AdapterConfig(id="github-trending", type="GitHubTrendingAdapter"),
        AdapterConfig(id="follow-api", type="FollowApiAdapter"),
        AdapterConfig(id="ai-search", type="AISearchAdapter"),
        AdapterConfig(id="rss-adapter", type="RSSAdapter"),
    ]


def _default_publishers() -> list[PublisherConfig]:
    return [
        PublisherConfig(id="feishu_bot", type="feishu_bot", enabled=False),
        PublisherConfig(id="wecom_bot", type="wecom_bot", enabled=False),
        PublisherConfig(id="github", type="github", enabled=False),
        PublisherConfig(id="wechat", type="wechat", enabled=False),
        PublisherConfig(id="rss", type="rss", enabled=False),
    ]


def _default_storages() -> list[StorageConfig]:
    return [
        StorageConfig(id="r2", type="r2", enabled=False),
        StorageConfig(id="github_storage", type="github_storage", enabled=False),
    ]


class SystemSettings(BaseSettings):
    """System settings loaded from defaults, dotenv, and environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="MULTISCRIBE_",
        env_file=".env",
        extra="allow",
    )

    system_password: str = ""
    jwt_secret: str = ""
    db_path: str = "data/database.sqlite"
    log_level: str = "INFO"
    active_ai_provider_id: str = ""
    http_proxy: str = ""
    ai_providers: list[ProviderConfig] = Field(default_factory=_default_ai_providers)
    adapters: list[AdapterConfig] = Field(default_factory=_default_adapters)
    publishers: list[PublisherConfig] = Field(default_factory=_default_publishers)
    storages: list[StorageConfig] = Field(default_factory=_default_storages)
    closed_plugins: list[str] = Field(default_factory=list)
    selection_fetch_days: int = 2
    selection_query_field: str = "ingestion_date"


DEFAULT_SETTINGS = SystemSettings.model_construct()


class ConfigService:
    """Compose default, environment, and persistent configuration layers."""

    def __init__(self, kv_repository: KvRepositoryPort | None = None) -> None:
        """Create a service with an optional persistent settings repository."""
        self._kv_repository = kv_repository

    def get_settings(self) -> SystemSettings:
        """Load defaults and apply dotenv or process-environment values."""
        return SystemSettings()

    async def load_overrides(self) -> dict[str, Any]:
        """Load persisted system settings overrides when a KV repository is configured."""
        if self._kv_repository is None:
            return {}
        value = await self._kv_repository.get("system_settings")
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ConfigError("system_settings override must be a JSON object")
        return cast(dict[str, Any], value)

    async def save_settings(self, settings_dict: dict[str, Any]) -> None:
        """Persist system settings overrides through the configured KV repository."""
        if self._kv_repository is None:
            raise ConfigError("persistent settings require a KV repository")
        await self._kv_repository.set("system_settings", settings_dict)

    async def get_settings_with_overrides(self) -> SystemSettings:
        """Load settings and apply the current persistent override mapping."""
        settings = self.get_settings()
        overrides = await self.load_overrides()
        if not overrides:
            return settings

        merged = settings.model_dump()
        merged.update(overrides)
        return SystemSettings.model_validate(merged)


_CONFIG_SERVICE = ConfigService()


def get_settings() -> SystemSettings:
    """Return current settings through the process-wide configuration service."""
    return _CONFIG_SERVICE.get_settings()
