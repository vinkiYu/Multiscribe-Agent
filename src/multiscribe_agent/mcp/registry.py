"""Small typed registry for MCP-facing tool handlers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel

type ToolHandler = Callable[[dict[str, object]], Awaitable[dict[str, object]]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One externally discoverable MCP tool."""

    name: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel] | None
    handler: ToolHandler


@dataclass(slots=True)
class MCPToolRegistry:
    """Register and resolve MCP tool specifications by stable tool name."""

    tools: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> None:
        """Register or replace one tool specification."""
        self.tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        """Return one tool specification or raise KeyError."""
        return self.tools[name]

    def list_tools(self) -> list[ToolSpec]:
        """Return tools sorted by stable name for deterministic discovery."""
        return [self.tools[name] for name in sorted(self.tools)]

    def clear(self) -> None:
        """Remove registered specs for reload and test isolation."""
        self.tools.clear()
