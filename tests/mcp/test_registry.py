"""Neutral MCP tool-registry coverage."""

from __future__ import annotations

import pytest

from multiscribe_agent.mcp.registry import MCPToolRegistry, ToolSpec
from multiscribe_agent.mcp.types import EmptyInput


@pytest.mark.asyncio
async def test_registry_orders_replaces_and_clears_tools() -> None:
    """Registry names are deterministic and replacement is keyed by name."""

    async def handler(_: dict[str, object]) -> dict[str, object]:
        return {"ok": True}

    registry = MCPToolRegistry()
    registry.register(ToolSpec("b", "B", EmptyInput, None, handler))
    registry.register(ToolSpec("a", "A", EmptyInput, None, handler))
    registry.register(ToolSpec("b", "Replacement", EmptyInput, None, handler))
    assert [tool.name for tool in registry.list_tools()] == ["a", "b"]
    assert registry.get("b").description == "Replacement"
    assert await registry.get("a").handler({}) == {"ok": True}
    registry.clear()
    assert registry.list_tools() == []
