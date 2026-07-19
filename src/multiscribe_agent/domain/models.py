"""Shared domain data contracts for MultiscribeAgent."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Dynamic metadata and provider payloads are explicit JSON integration boundaries.
type JsonObject = dict[str, Any]


class _DomainModel(BaseModel):
    """Base class for mutable domain contracts."""

    model_config = ConfigDict(frozen=False)


class UnifiedData(_DomainModel):
    """Canonical content item passed between adapters, agents, and publishers."""

    id: str
    title: str
    url: str
    description: str
    published_date: str
    ingestion_date: str | None = None
    source: str
    category: str
    author: str | None = None
    status: str | None = None
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("id", "published_date")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class ToolCall(_DomainModel):
    """Provider-neutral request to execute a named tool."""

    id: str
    name: str
    arguments: JsonObject | str


class TokenUsage(_DomainModel):
    """Token accounting returned by an AI provider."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


class InteropKey(_DomainModel):
    """Persisted credential for external AI tool interoperability."""

    model_config = ConfigDict(frozen=True)

    key_id: str
    key_hash: str
    description: str = ""
    created_at: int
    approved: bool = False
    rate_limit_per_minute: int = Field(default=60, ge=1)
    last_used_at: int | None = None
    request_count: int = Field(default=0, ge=0)


class AIMessage(_DomainModel):
    """Provider-neutral message exchanged with an AI model."""

    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class AIResponse(_DomainModel):
    """Provider-neutral AI completion result."""

    content: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: TokenUsage | None = None
    raw: JsonObject | None = None


class AgentDefinition(_DomainModel):
    """Declarative configuration for an executable agent."""

    id: str
    name: str
    description: str
    system_prompt: str
    provider_id: str
    model: str
    temperature: float = 0.7
    tool_ids: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    mcp_server_ids: list[str] = Field(default_factory=list)
    streaming: bool = False
    is_hidden: bool = False
    category: str | None = None


class WorkflowStep(_DomainModel):
    """One agent or nested-workflow node in a workflow definition."""

    id: str
    name: str
    step_type: Literal["agent", "workflow"]
    agent_id: str | None = None
    workflow_id: str | None = None
    input_map: dict[str, str] | None = None
    next_step_id: str | None = None
    next_step_ids: list[str] | None = None
    enabled: bool = True
    config: JsonObject = Field(default_factory=dict)
    max_iterations: int | None = None
    exit_condition: str | None = None


class WorkflowDefinition(_DomainModel):
    """Declarative workflow composed of ordered or branching steps."""

    id: str
    name: str
    description: str
    steps: list[WorkflowStep]


class ToolDefinition(_DomainModel):
    """Tool metadata and JSON Schema parameters exposed to an agent."""

    id: str
    name: str
    description: str
    parameters: JsonObject = Field(default_factory=dict)
    is_builtin: bool = False


class MCPConfig(_DomainModel):
    """Connection settings for an MCP server."""

    id: str
    name: str
    transport: Literal["stdio", "sse", "streamable_http"]
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class SkillFrontmatter(_DomainModel):
    """Metadata parsed from the frontmatter of a skill document."""

    name: str
    description: str
    bins: list[str] = Field(default_factory=list)


class SkillEntry(_DomainModel):
    """A discovered skill and its executable instructions."""

    id: str
    name: str
    description: str
    instructions: str
    is_builtin: bool
    frontmatter: SkillFrontmatter
    dir_path: str | None = None
    files: list[str] = Field(default_factory=list)


class SourceData(_DomainModel):
    """Persisted content item enriched with ingestion metadata."""

    id: str
    title: str
    url: str
    description: str
    published_date: str
    source: str
    category: str
    author: str | None = None
    metadata: JsonObject = Field(default_factory=dict)
    fetched_at: str
    ingestion_date: str
    adapter_name: str
    status: str | None = None


class TaskLog(_DomainModel):
    """Lifecycle record for one scheduled or manually triggered task."""

    id: str | None = None
    task_id: str
    task_name: str
    start_time: str | None
    end_time: str | None = None
    duration_ms: int | None = None
    status: Literal["running", "success", "error", "interrupted"]
    progress: float | None = None
    message: str | None = None
    result_count: int | None = None


class CommitRecord(_DomainModel):
    """History record for content published to an external platform."""

    date: str
    platform: str
    file_path: str
    commit_message: str
    commit_time: str
    full_content: str


class ScheduleTask(_DomainModel):
    """Cron-based task definition managed by the scheduler."""

    id: str
    name: str
    task_type: Literal[
        "full_ingestion",
        "adapter",
        "agent_summary",
        "agent_deal",
        "daily_digest",
    ]
    cron: str
    enabled: bool = True
    config: JsonObject = Field(default_factory=dict)
    last_run: str | None = None
    last_status: str | None = None
    last_error: str | None = None


class MemoryEntry(_DomainModel):
    """Stored agent memory used by the future memory service."""

    id: str
    content: str
    importance: int
    tags: list[str] = Field(default_factory=list)
    created_at: int
    agent_id: str | None = None
    metadata: JsonObject = Field(default_factory=dict)


class KBCategory(_DomainModel):
    """Knowledge-base category summary."""

    id: str
    name: str
    description: str
    document_count: int
    last_updated_at: int


class KBDocument(_DomainModel):
    """Document metadata stored in the knowledge base."""

    id: str
    category_id: str
    name: str
    file_name: str
    type: str
    summary: str
    chunk_count: int
    created_at: int
    updated_at: int
    metadata: JsonObject = Field(default_factory=dict)


class KBChunk(_DomainModel):
    """Searchable chunk belonging to a knowledge-base document."""

    id: str
    document_id: str
    content: str
    index: int
    metadata: JsonObject = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Plugin contracts (shared by plugins/base.py, registries, and discovery).
# Defined here in the domain layer so plugin code depends on domain, not the
# reverse. See docs/conventions/plugin-contract.md.
# ---------------------------------------------------------------------------

PluginType = Literal["adapter", "publisher", "storage", "tool"]


class ConfigField(_DomainModel):
    """Declarative description of one configuration value exposed by a plugin.

    Drives both runtime validation and the future settings UI. ``scope``
    distinguishes adapter/publisher-level shared config from per-item config.
    """

    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    type: Literal["text", "password", "textarea", "select", "boolean", "number", "url"]
    required: bool = False
    default: Any = None
    options: list[str] | None = None
    placeholder: str = ""
    help_text: str = ""
    scope: Literal["adapter", "item"] = "adapter"


class PluginMetadata(_DomainModel):
    """Self-describing metadata carried by every plugin class.

    Discovery registers any class exposing a ``metadata`` ClassVar of this type.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    type: PluginType
    name: str
    description: str
    icon: str = ""
    config_fields: list[ConfigField] = Field(default_factory=list)
    is_builtin: bool = True
