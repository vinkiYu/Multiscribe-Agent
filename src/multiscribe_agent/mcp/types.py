"""Validated MCP tool input and output schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EmptyInput(BaseModel):
    """Empty object input accepted by read-only listing tools."""


class FetchRSSInput(BaseModel):
    """Input for one adapter-triggering MCP request."""

    adapter_id: str
    config: dict[str, object] = Field(default_factory=dict)
    max_items: int = Field(default=20, ge=1, le=100)


class FetchRSSOutput(BaseModel):
    """Normalized response from the RSS fetch tool."""

    adapter_id: str
    fetched_count: int
    items: list[dict[str, object]]


class KBSearchInput(BaseModel):
    """Input for one knowledge-base retrieval request."""

    query: str
    top_k: int = Field(default=10, ge=1, le=50)
    category_id: str | None = None


class KBSearchOutput(BaseModel):
    """Search response with degradation and capability details."""

    hits: list[dict[str, object]]
    degraded: bool
    capabilities: dict[str, bool]


class DigestHistoryInput(BaseModel):
    """Input for bounded published-delivery history lookup."""

    publisher_id: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    from_date: str | None = None
    to_date: str | None = None


class DigestHistoryOutput(BaseModel):
    """Bounded publish-history response."""

    records: list[dict[str, object]]


class ListSourcesOutput(BaseModel):
    """Discovered adapter metadata and enabled state."""

    sources: list[dict[str, object]]


class ListPublishersOutput(BaseModel):
    """Discovered publisher metadata and enabled state."""

    publishers: list[dict[str, object]]


class MCPAuthError(RuntimeError):
    """Raised when the required MCP API key is absent or incorrect."""
