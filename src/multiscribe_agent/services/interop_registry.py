"""Register and dispatch tools exposed to external AI clients."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from multiscribe_agent.bootstrap import ServiceContext

type ToolHandler = Callable[[dict[str, object]], Awaitable[dict[str, object]]]


@dataclass(frozen=True, slots=True)
class ToolSchema:
    """OpenAI Function Calling schema for one interop tool."""

    name: str
    description: str
    parameters: dict[str, object]


class UnknownToolError(KeyError):
    """Raised when an external AI requests an unregistered tool."""


class ToolRegistry:
    """In-process tool registry safe to share across requests."""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolSchema, ToolHandler]] = {}

    def register(self, schema: ToolSchema, handler: ToolHandler) -> None:
        """Register or replace a tool handler by stable name."""
        self._tools[schema.name] = (schema, handler)

    def list_schemas(self) -> list[dict[str, object]]:
        """Return OpenAI function-tool objects."""
        return [
            {
                "type": "function",
                "function": {
                    "name": schema.name,
                    "description": schema.description,
                    "parameters": schema.parameters,
                },
            }
            for schema, _ in self._tools.values()
        ]

    async def execute(self, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        """Execute one registered tool with already decoded arguments."""
        entry = self._tools.get(tool_name)
        if entry is None:
            raise UnknownToolError(f"unknown tool: {tool_name}")
        return await entry[1](arguments)


def build_default_registry(context: ServiceContext) -> ToolRegistry:
    """Create the default registry with current context-bound handlers."""
    registry = ToolRegistry()
    registry.register(
        ToolSchema(
            name="list_sources",
            description="List all configured content sources (RSS, GitHub, AI search).",
            parameters={"type": "object", "properties": {}, "required": []},
        ),
        lambda _args: _list_sources_handler(),
    )
    registry.register(
        ToolSchema(
            name="kb_search",
            description="Search the persistent knowledge base by query.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                },
                "required": ["query"],
            },
        ),
        lambda args: _kb_search_handler(context, args),
    )
    registry.register(
        ToolSchema(
            name="list_publishers",
            description="List configured publishers (Feishu, WeCom, WeChat, ...).",
            parameters={"type": "object", "properties": {}, "required": []},
        ),
        lambda _args: _list_publishers_handler(),
    )
    return registry


async def _list_sources_handler() -> dict[str, object]:
    from multiscribe_agent.plugins.registry import AdapterRegistry

    return {
        "sources": [
            {"id": metadata.id, "name": metadata.name, "kind": "adapter"}
            for metadata in AdapterRegistry.get_instance().list_metadata()
        ]
    }


async def _kb_search_handler(context: ServiceContext, args: dict[str, object]) -> dict[str, object]:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    top_k = args.get("top_k", 10)
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 50:
        raise ValueError("top_k must be an integer from 1 to 50")
    if context.kb_service is None:
        return {"hits": [], "degraded": True}
    hits = await context.kb_service.search(query, top_k=top_k)
    return {
        "hits": [
            {
                "chunk_id": hit.chunk_id,
                "document_id": hit.document_id,
                "content": hit.content,
                "score": hit.score,
            }
            for hit in hits
        ],
        "degraded": context.kb_service.capabilities.degraded,
    }


async def _list_publishers_handler() -> dict[str, object]:
    from multiscribe_agent.plugins.registry import PublisherRegistry

    return {
        "publishers": [
            {"id": metadata.id, "name": metadata.name, "kind": "publisher"}
            for metadata in PublisherRegistry.get_instance().list_metadata()
        ]
    }
