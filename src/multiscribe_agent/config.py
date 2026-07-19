"""Application settings and layered configuration access."""

from __future__ import annotations

from typing import Annotated, Any, Literal, cast

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from multiscribe_agent.core.errors import ConfigError
from multiscribe_agent.domain.ports import KvRepository as KvRepositoryPort


class ProviderConfig(BaseModel):
    """Configuration for one AI provider endpoint.

    A single endpoint (one api_key + base_url) may serve multiple models; ``models``
    is a documented/UI-selectable model catalog, not a runtime allowlist. The
    concrete model used per call is supplied by ``AgentDefinition.model`` and
    injected into the provider at construction time, where the remote endpoint
    determines whether it is available.
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
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_API_KEY", "MULTISCRIBE_OPENAI_API_KEY"),
    )
    openai_api_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_API_BASE_URL", "MULTISCRIBE_OPENAI_API_BASE_URL"),
    )
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "MULTISCRIBE_ANTHROPIC_API_KEY"),
    )
    anthropic_api_base_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "ANTHROPIC_API_BASE_URL", "MULTISCRIBE_ANTHROPIC_API_BASE_URL"
        ),
    )
    google_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_API_KEY", "MULTISCRIBE_GOOGLE_API_KEY"),
    )
    feishu_webhook: str = Field(
        default="",
        validation_alias=AliasChoices("FEISHU_WEBHOOK", "MULTISCRIBE_FEISHU_WEBHOOK"),
    )
    feishu_secret: str = Field(
        default="",
        validation_alias=AliasChoices("FEISHU_SECRET", "MULTISCRIBE_FEISHU_SECRET"),
    )
    wecom_webhook: str = Field(
        default="",
        validation_alias=AliasChoices("WECOM_WEBHOOK", "MULTISCRIBE_WECOM_WEBHOOK"),
    )
    db_path: str = "data/database.sqlite"
    log_level: str = "INFO"
    active_ai_provider_id: str = ""
    http_proxy: str = Field(
        default="",
        validation_alias=AliasChoices("HTTP_PROXY", "MULTISCRIBE_HTTP_PROXY"),
    )
    default_curation_provider_id: str = Field(
        default="default-openai",
        validation_alias=AliasChoices(
            "DEFAULT_CURATION_PROVIDER_ID", "MULTISCRIBE_DEFAULT_CURATION_PROVIDER_ID"
        ),
    )
    default_curation_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices(
            "DEFAULT_CURATION_MODEL", "MULTISCRIBE_DEFAULT_CURATION_MODEL"
        ),
    )
    default_curation_temperature: float = Field(
        default=0.3,
        validation_alias=AliasChoices(
            "DEFAULT_CURATION_TEMPERATURE", "MULTISCRIBE_DEFAULT_CURATION_TEMPERATURE"
        ),
    )
    default_digest_targets: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["feishu_bot", "wecom_bot"],
        validation_alias=AliasChoices(
            "DEFAULT_DIGEST_TARGETS", "MULTISCRIBE_DEFAULT_DIGEST_TARGETS"
        ),
    )
    default_digest_top_n: int = Field(
        default=5,
        validation_alias=AliasChoices("DEFAULT_DIGEST_TOP_N", "MULTISCRIBE_DEFAULT_DIGEST_TOP_N"),
    )
    default_digest_fetch_days: int = Field(
        default=2,
        validation_alias=AliasChoices(
            "DEFAULT_DIGEST_FETCH_DAYS", "MULTISCRIBE_DEFAULT_DIGEST_FETCH_DAYS"
        ),
    )
    default_digest_adapter_ids: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["rss-adapter"],
        validation_alias=AliasChoices(
            "DEFAULT_DIGEST_ADAPTER_IDS", "MULTISCRIBE_DEFAULT_DIGEST_ADAPTER_IDS"
        ),
    )
    memory_importance_threshold: int = Field(default=5, ge=0, le=10)
    memory_default_push_time: str = "09:00"
    mcp_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("MCP_API_KEY", "MULTISCRIBE_MCP_API_KEY"),
    )
    mcp_default_host: str = "127.0.0.1"
    mcp_default_port: int = Field(default=8765, ge=1, le=65535)
    mcp_transport: Literal["stdio", "sse"] = "stdio"
    ai_providers: list[ProviderConfig] = Field(default_factory=_default_ai_providers)
    adapters: list[AdapterConfig] = Field(default_factory=_default_adapters)
    publishers: list[PublisherConfig] = Field(default_factory=_default_publishers)
    storages: list[StorageConfig] = Field(default_factory=_default_storages)
    closed_plugins: list[str] = Field(default_factory=list)
    selection_fetch_days: int = 2
    selection_query_field: str = "ingestion_date"

    @field_validator("default_digest_targets", "default_digest_adapter_ids", mode="before")
    @classmethod
    def _parse_csv_settings(cls, value: object) -> object:
        """Accept comma-separated dotenv values for the two list-based MVP defaults."""
        if not isinstance(value, str):
            return value
        return [item.strip() for item in value.split(",") if item.strip()]

    @model_validator(mode="after")
    def _bind_mvp_environment_values(self) -> SystemSettings:
        """Copy flat dotenv credentials into the existing structured runtime settings."""
        api_keys = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "google": self.google_api_key,
        }
        api_base_urls = {
            "openai": self.openai_api_base_url,
            "anthropic": self.anthropic_api_base_url,
        }
        for provider in self.ai_providers:
            api_key = api_keys.get(provider.type, "")
            if api_key:
                provider.api_key = api_key
            api_base_url = api_base_urls.get(provider.type, "")
            if api_base_url:
                provider.base_url = api_base_url

        for publisher in self.publishers:
            if publisher.id == "feishu_bot":
                if self.feishu_webhook:
                    publisher.config["webhook"] = self.feishu_webhook
                    publisher.enabled = True
                if self.feishu_secret:
                    publisher.config["secret"] = self.feishu_secret
            elif publisher.id == "wecom_bot" and self.wecom_webhook:
                publisher.config["webhook"] = self.wecom_webhook
                publisher.enabled = True
        return self


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
