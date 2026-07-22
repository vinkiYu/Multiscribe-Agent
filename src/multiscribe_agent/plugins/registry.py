"""Singleton registries for discovered plugin classes and tool instances."""

from __future__ import annotations

import builtins
from collections.abc import Mapping

import structlog

from multiscribe_agent.core.errors import ToolApprovalRequired
from multiscribe_agent.domain.models import PluginMetadata, ToolCall, ToolDefinition
from multiscribe_agent.plugins.base import (
    PLUGIN_API_VERSION,
    BaseAdapter,
    BasePublisher,
    BaseStorageProvider,
    BaseTool,
)
from multiscribe_agent.plugins.security import (
    ToolApprovalStore,
    normalize_arguments,
    tool_call_fingerprint,
    validate_arguments,
)

log = structlog.get_logger(__name__)


class IncompatiblePluginError(RuntimeError):
    """Raised when a plugin declares an unsupported Plugin API version."""


def _check_compatibility(metadata: PluginMetadata) -> None:
    """Reject plugin metadata that cannot satisfy the current plugin contract."""
    if metadata.api_version != PLUGIN_API_VERSION:
        raise IncompatiblePluginError(
            f"plugin {metadata.id} api_version={metadata.api_version} "
            f"but system requires {PLUGIN_API_VERSION}"
        )


class _ClassRegistry[PluginT]:
    """Store plugin classes and immutable metadata by stable key."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[type[PluginT], PluginMetadata]] = {}

    def register(self, key: str, plugin_class: type[PluginT], metadata: PluginMetadata) -> None:
        """Register or replace a plugin class under a stable key."""
        _check_compatibility(metadata)
        self._entries[key] = (plugin_class, metadata)

    def get(self, key: str) -> type[PluginT]:
        """Return a registered class.

        Raises:
            KeyError: If no class is registered under the key.
        """
        return self._entries[key][0]

    def get_metadata(self, key: str) -> PluginMetadata:
        """Return metadata for a registered key."""
        return self._entries[key][1]

    def list(self) -> builtins.list[type[PluginT]]:
        """Return registered classes in insertion order."""
        return [entry[0] for entry in self._entries.values()]

    def list_metadata(self) -> builtins.list[PluginMetadata]:
        """Return registered metadata in insertion order."""
        return [entry[1] for entry in self._entries.values()]

    def clear(self) -> None:
        """Remove all entries, primarily for reload and test isolation."""
        self._entries.clear()


_adapter_instance: AdapterRegistry | None = None
_publisher_instance: PublisherRegistry | None = None
_storage_instance: StorageRegistry | None = None
_tool_instance: ToolRegistry | None = None


class AdapterRegistry(_ClassRegistry[BaseAdapter]):
    """Singleton registry for adapter plugin classes."""

    @classmethod
    def get_instance(cls) -> AdapterRegistry:
        """Return the process-wide adapter registry."""
        global _adapter_instance
        if _adapter_instance is None:
            _adapter_instance = cls()
        return _adapter_instance


class PublisherRegistry(_ClassRegistry[BasePublisher]):
    """Singleton registry for publisher plugin classes."""

    @classmethod
    def get_instance(cls) -> PublisherRegistry:
        """Return the process-wide publisher registry."""
        global _publisher_instance
        if _publisher_instance is None:
            _publisher_instance = cls()
        return _publisher_instance


class StorageRegistry(_ClassRegistry[BaseStorageProvider]):
    """Singleton registry for storage plugin classes."""

    @classmethod
    def get_instance(cls) -> StorageRegistry:
        """Return the process-wide storage registry."""
        global _storage_instance
        if _storage_instance is None:
            _storage_instance = cls()
        return _storage_instance


class ToolRegistry:
    """Singleton registry with separate tool class and initialized instance stores."""

    def __init__(self, approval_store: ToolApprovalStore | None = None) -> None:
        self._classes: dict[str, tuple[type[BaseTool], PluginMetadata]] = {}
        self._tools: dict[str, BaseTool] = {}
        self._approval_store = approval_store or ToolApprovalStore()

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        """Return the process-wide tool registry."""
        global _tool_instance
        if _tool_instance is None:
            _tool_instance = cls()
        return _tool_instance

    def register(self, tool_class: type[BaseTool], metadata: PluginMetadata | None = None) -> None:
        """Register or replace a tool class without instantiating it."""
        resolved = metadata or tool_class.metadata
        _check_compatibility(resolved)
        self._classes[resolved.id] = (tool_class, resolved)

    def register_tool(self, tool: BaseTool) -> None:
        """Register an initialized tool instance for runtime calls."""
        self._tools[tool.id] = tool
        if tool.id not in self._classes:
            self.register(type(tool), tool.metadata)

    def get_class(self, tool_id: str) -> type[BaseTool]:
        """Return a discovered tool class without instantiating it."""
        return self._classes[tool_id][0]

    def get_tool(self, tool_id: str) -> BaseTool:
        """Return an initialized tool instance."""
        return self._tools[tool_id]

    async def call_tool(self, tool_id: str, args: Mapping[str, object]) -> object:
        """Call a low-risk initialized tool by id through the secure boundary."""
        return await self.execute(ToolCall(id="direct", name=tool_id, arguments=dict(args)))

    def approve(self, tool_call: ToolCall, *, ttl_seconds: float = 300) -> str:
        """Issue a one-time operator approval for an exact high-risk call."""
        tool = self._find_tool(tool_call.name)
        arguments = normalize_arguments(tool_call.arguments)
        validate_arguments(arguments, tool.parameters)
        if not tool.requires_approval:
            raise ValueError(f"tool does not require approval: {tool.id}")
        return self._approval_store.approve(tool_call, ttl_seconds=ttl_seconds)

    def get_all_tools(self) -> list[ToolDefinition]:
        """Return Agent-facing definitions for initialized tools."""
        return [self._to_definition(tool) for tool in self._tools.values()]

    def get_definitions(self, tool_ids: list[str]) -> list[ToolDefinition]:
        """Return initialized definitions selected by id for the P4 Harness."""
        definitions = {definition.id: definition for definition in self.get_all_tools()}
        return [definitions[tool_id] for tool_id in tool_ids if tool_id in definitions]

    async def execute(self, tool_call: ToolCall, *, approval_token: str | None = None) -> object:
        """Execute a P4 Harness tool call by exposed name or stable id."""
        tool = self._find_tool(tool_call.name)
        arguments = normalize_arguments(tool_call.arguments)
        validate_arguments(arguments, tool.parameters)
        fingerprint = tool_call_fingerprint(tool_call)[:16]
        if tool.requires_approval and not self._approval_store.consume(tool_call, approval_token):
            log.warning(
                "tool_approval_required",
                tool_id=tool.id,
                risk_level=tool.risk_level,
                call_fingerprint=fingerprint,
            )
            raise ToolApprovalRequired(f"operator approval required for tool: {tool.id}")
        log.info(
            "tool_execution_audit",
            tool_id=tool.id,
            risk_level=tool.risk_level,
            approved=tool.requires_approval,
            call_fingerprint=fingerprint,
        )
        return await tool.handler(arguments)

    def list_metadata(self) -> list[PluginMetadata]:
        """Return metadata for discovered tool classes."""
        return [entry[1] for entry in self._classes.values()]

    def clear(self) -> None:
        """Remove all discovered classes and initialized instances."""
        self._classes.clear()
        self._tools.clear()

    def _find_tool(self, name: str) -> BaseTool:
        tool = next(
            (
                candidate
                for candidate in self._tools.values()
                if candidate.name == name or candidate.id == name
            ),
            None,
        )
        if tool is None:
            raise KeyError(name)
        return tool

    @staticmethod
    def _to_definition(tool: BaseTool) -> ToolDefinition:
        return ToolDefinition(
            id=tool.id,
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters,
            is_builtin=tool.is_builtin,
            risk_level=tool.risk_level,
            requires_approval=tool.requires_approval,
            read_only=tool.read_only,
            idempotent=tool.idempotent,
        )
