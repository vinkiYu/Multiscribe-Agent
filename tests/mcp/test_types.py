"""Pydantic input-schema boundary coverage for MCP tools."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from multiscribe_agent.mcp.registry import MCPToolRegistry
from multiscribe_agent.mcp.types import DigestHistoryInput, FetchRSSInput, KBSearchInput


def test_mcp_input_models_enforce_documented_limits() -> None:
    """RSS, KB, and history bounds reject unsafe client-provided limits."""
    with pytest.raises(ValidationError):
        FetchRSSInput(adapter_id="rss", max_items=101)
    with pytest.raises(ValidationError):
        KBSearchInput(query="q", top_k=0)
    with pytest.raises(ValidationError):
        DigestHistoryInput(limit=201)


def test_mcp_registry_raises_for_unknown_tool() -> None:
    """Unknown MCP names are not silently accepted by the registry."""
    with pytest.raises(KeyError):
        MCPToolRegistry().get("missing")
