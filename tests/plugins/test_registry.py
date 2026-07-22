"""Tests for singleton class registries and ToolRegistry dual registration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar, Literal

import pytest

from multiscribe_agent.core.errors import ToolApprovalRequired, ToolExecutionError
from multiscribe_agent.domain.models import PluginMetadata, ToolCall
from multiscribe_agent.plugins.base import BaseAdapter, BaseTool
from multiscribe_agent.plugins.registry import AdapterRegistry, ToolRegistry


class FirstAdapter(BaseAdapter):
    """Concrete adapter used for registry identity tests."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="adapter", type="adapter", name="First", description="First adapter."
    )

    async def fetch(self, config: Mapping[str, object]) -> object:
        return config

    def transform(self, raw: object, config: Mapping[str, object] | None = None) -> list:
        del raw, config
        return []


class ReplacementAdapter(FirstAdapter):
    """Replacement class sharing the same registry key."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="adapter", type="adapter", name="Replacement", description="Replacement adapter."
    )


class EchoTool(BaseTool):
    """Initialized test tool for ToolRegistry calls."""

    id: ClassVar[str] = "echo_tool"
    name: ClassVar[str] = "echo_tool"
    description: ClassVar[str] = "Echo one value."
    parameters: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {"value": {}},
        "required": ["value"],
    }
    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id=id, type="tool", name="Echo", description=description
    )

    async def handler(self, args: Mapping[str, object]) -> object:
        return args["value"]


class RiskyTool(EchoTool):
    """Tool requiring an out-of-band approval grant."""

    id: ClassVar[str] = "risky_tool"
    name: ClassVar[str] = "risky_tool"
    requires_approval: ClassVar[bool] = True
    risk_level: ClassVar[Literal["high"]] = "high"
    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id=id, type="tool", name="Risky", description="Risky test tool."
    )


def test_class_registry_singleton_register_get_and_overwrite() -> None:
    """Registration exposes classes/metadata and replacement is idempotent."""
    registry = AdapterRegistry.get_instance()
    assert registry is AdapterRegistry.get_instance()

    registry.register("adapter", FirstAdapter, FirstAdapter.metadata)
    assert registry.get("adapter") is FirstAdapter
    assert registry.list() == [FirstAdapter]
    assert registry.list_metadata() == [FirstAdapter.metadata]

    registry.register("adapter", ReplacementAdapter, ReplacementAdapter.metadata)
    assert registry.get("adapter") is ReplacementAdapter
    assert registry.list_metadata() == [ReplacementAdapter.metadata]


@pytest.mark.asyncio
async def test_tool_registry_dual_registration_and_call() -> None:
    """Tool class discovery and initialized calls are kept as separate stages."""
    registry = ToolRegistry.get_instance()
    registry.register(EchoTool)
    assert registry.get_class("echo_tool") is EchoTool
    assert registry.list_metadata() == [EchoTool.metadata]

    tool = EchoTool()
    registry.register_tool(tool)
    assert registry.get_tool("echo_tool") is tool
    assert await registry.call_tool("echo_tool", {"value": "hello"}) == "hello"
    assert registry.get_all_tools()[0].name == "echo_tool"
    assert registry.get_definitions(["echo_tool", "missing"])[0].id == "echo_tool"
    assert (
        await registry.execute(
            ToolCall(id="call-1", name="echo_tool", arguments={"value": "from harness"})
        )
        == "from harness"
    )


@pytest.mark.asyncio
async def test_registry_validates_schema_before_handler() -> None:
    registry = ToolRegistry()
    registry.register_tool(EchoTool())
    with pytest.raises(ToolExecutionError, match="missing required"):
        await registry.execute(ToolCall(id="bad", name="echo_tool", arguments={}))


@pytest.mark.asyncio
async def test_high_risk_approval_is_exact_and_one_time() -> None:
    registry = ToolRegistry()
    registry.register_tool(RiskyTool())
    call = ToolCall(id="risk", name="risky_tool", arguments={"value": "approved"})
    with pytest.raises(ToolApprovalRequired):
        await registry.execute(call)

    token = registry.approve(call)
    changed = ToolCall(id="changed", name="risky_tool", arguments={"value": "different"})
    with pytest.raises(ToolApprovalRequired):
        await registry.execute(changed, approval_token=token)
    assert await registry.execute(call, approval_token=token) == "approved"
    with pytest.raises(ToolApprovalRequired):
        await registry.execute(call, approval_token=token)
