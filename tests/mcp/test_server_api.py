"""MCP server assembly and JWT REST mirror coverage."""

from __future__ import annotations

import httpx
import pytest

from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings
from multiscribe_agent.mcp.server import build_tool_registry


@pytest.mark.asyncio
async def test_server_builds_all_five_documented_tools() -> None:
    """Assembly binds all documented MCP names to the initialized context."""
    context = ServiceContext(SystemSettings(_env_file=None, db_path=":memory:"))
    await context.init()
    try:
        names = [tool.name for tool in build_tool_registry(context, context.settings).list_tools()]
        assert names == [
            "multiscribe_digest_history",
            "multiscribe_fetch_rss",
            "multiscribe_knowledge_search",
            "multiscribe_list_publishers",
            "multiscribe_list_sources",
        ]
    finally:
        await context.close()


@pytest.mark.asyncio
async def test_mcp_rest_api_requires_jwt_and_lists_and_calls_tools() -> None:
    """REST mirror exposes discovery and authenticated invocation."""
    settings = SystemSettings(_env_file=None, db_path=":memory:")
    context = ServiceContext(settings)
    await context.init()
    try:
        app = create_app(settings, context)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/mcp/tools")).status_code == 401
            token = (await client.post("/api/login", json={"password": "admin123"})).json()[
                "access_token"
            ]
            headers = {"Authorization": f"Bearer {token}"}
            listed = await client.get("/api/mcp/tools", headers=headers)
            sources = await client.post(
                "/api/mcp/tools/multiscribe_list_sources/call", headers=headers, json={}
            )
            missing = await client.post("/api/mcp/tools/missing/call", headers=headers, json={})
        assert len(listed.json()) == 5
        assert "sources" in sources.json()
        assert missing.status_code == 404
    finally:
        await context.close()
