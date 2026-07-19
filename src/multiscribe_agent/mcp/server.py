"""MCP server assembly for stdio and SSE transports."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

from starlette.types import Receive, Scope, Send

from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings, get_settings
from multiscribe_agent.mcp.auth import get_required_api_key, verify_api_key
from multiscribe_agent.mcp.registry import MCPToolRegistry, ToolSpec
from multiscribe_agent.mcp.tools.digest_tools import digest_history
from multiscribe_agent.mcp.tools.kb_tools import knowledge_search
from multiscribe_agent.mcp.tools.publisher_tools import list_publishers, list_sources
from multiscribe_agent.mcp.tools.rss_tools import fetch_rss
from multiscribe_agent.mcp.types import (
    DigestHistoryInput,
    DigestHistoryOutput,
    EmptyInput,
    FetchRSSInput,
    FetchRSSOutput,
    KBSearchInput,
    KBSearchOutput,
    ListPublishersOutput,
    ListSourcesOutput,
    MCPAuthError,
)

type ContextHandler = Callable[[dict[str, object], ServiceContext], Awaitable[dict[str, object]]]


def build_tool_registry(context: ServiceContext, settings: SystemSettings) -> MCPToolRegistry:
    """Bind all five documented tool handlers to one initialized service context."""
    registry = MCPToolRegistry()
    registry.register(
        _bound_spec(
            "multiscribe_fetch_rss",
            "Trigger one configured RSS adapter and return normalized items.",
            FetchRSSInput,
            FetchRSSOutput,
            fetch_rss,
            context,
        )
    )
    registry.register(
        _bound_spec(
            "multiscribe_knowledge_search",
            "Search the Multiscribe knowledge base with RRF or FTS fallback.",
            KBSearchInput,
            KBSearchOutput,
            knowledge_search,
            context,
        )
    )
    registry.register(
        _bound_spec(
            "multiscribe_digest_history",
            "Read bounded publisher delivery history.",
            DigestHistoryInput,
            DigestHistoryOutput,
            digest_history,
            context,
        )
    )
    registry.register(
        _settings_spec(
            "multiscribe_list_sources",
            "List configured sources.",
            ListSourcesOutput,
            list_sources,
            settings,
        )
    )
    registry.register(
        _settings_spec(
            "multiscribe_list_publishers",
            "List configured publishers.",
            ListPublishersOutput,
            list_publishers,
            settings,
        )
    )
    return registry


def _bound_spec(
    name: str,
    description: str,
    input_schema: type[FetchRSSInput] | type[KBSearchInput] | type[DigestHistoryInput],
    output_schema: type[FetchRSSOutput] | type[KBSearchOutput] | type[DigestHistoryOutput],
    handler: ContextHandler,
    context: ServiceContext,
) -> ToolSpec:
    """Bind a context-aware business handler to the neutral MCP registry."""

    async def bound(payload: dict[str, object]) -> dict[str, object]:
        return await handler(payload, context)

    return ToolSpec(name, description, input_schema, output_schema, bound)


def _settings_spec(
    name: str,
    description: str,
    output_schema: type[ListSourcesOutput] | type[ListPublishersOutput],
    handler: Callable[[dict[str, object], SystemSettings], Awaitable[dict[str, object]]],
    settings: SystemSettings,
) -> ToolSpec:
    """Bind a settings-only list handler to the neutral MCP registry."""

    async def bound(payload: dict[str, object]) -> dict[str, object]:
        return await handler(payload, settings)

    return ToolSpec(name, description, EmptyInput, output_schema, bound)


async def run_stdio_server() -> None:
    """Run the authenticated MCP protocol over stdio for desktop clients."""
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    settings = get_settings()
    expected_key = get_required_api_key(settings)
    context = ServiceContext(settings)
    await context.init()
    registry = build_tool_registry(context, settings)
    server = Server("multiscribe-agent")

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=spec.input_schema.model_json_schema(),
            )
            for spec in registry.list_tools()
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, object]) -> list[TextContent]:
        api_key = arguments.pop("_api_key", "")
        if not isinstance(api_key, str) or not verify_api_key(api_key, expected_key):
            raise MCPAuthError("invalid MCP_API_KEY")
        result = await registry.get(name).handler(arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await context.close()


async def run_sse_server(host: str, port: int) -> None:
    """Run the authenticated MCP protocol over the SDK's SSE transport."""
    import uvicorn
    from mcp.server import Server
    from mcp.server.sse import SseServerTransport
    from mcp.types import TextContent, Tool
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route

    settings = get_settings()
    expected_key = get_required_api_key(settings)
    context = ServiceContext(settings)
    await context.init()
    registry = build_tool_registry(context, settings)
    server = Server("multiscribe-agent")

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=spec.input_schema.model_json_schema(),
            )
            for spec in registry.list_tools()
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, object]) -> list[TextContent]:
        api_key = arguments.pop("_api_key", "")
        if not isinstance(api_key, str) or not verify_api_key(api_key, expected_key):
            raise MCPAuthError("invalid MCP_API_KEY")
        result = await registry.get(name).handler(arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    transport = SseServerTransport("/messages/")

    async def handle_sse(scope: Scope, receive: Receive, send: Send) -> None:
        async with transport.connect_sse(scope, receive, send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=transport.handle_post_message),
        ]
    )
    try:
        await asyncio.to_thread(uvicorn.run, app, host=host, port=port)
    finally:
        await context.close()
