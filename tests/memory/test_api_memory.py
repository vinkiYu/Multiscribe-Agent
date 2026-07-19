"""JWT-protected P17 API coverage."""

from __future__ import annotations

import httpx
import pytest

from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings


@pytest.mark.asyncio
async def test_memory_api_crud_search_preferences_and_extract() -> None:
    """All documented memory endpoints require JWT and perform core operations."""
    settings = SystemSettings(_env_file=None, db_path=":memory:")
    context = ServiceContext(settings)
    await context.init()
    try:
        app = create_app(settings, context)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/memory/preferences")).status_code == 401
            login = await client.post("/api/login", json={"password": "admin123"})
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            saved = await client.put(
                "/api/memory/preferences",
                headers=headers,
                json={
                    "preferred_tags": ["ai"],
                    "block_sources": ["noise"],
                    "push_time": "08:30",
                    "importance_threshold": 6,
                },
            )
            created = await client.post(
                "/api/memory/entries",
                headers=headers,
                json={"content": "API searchable memory", "importance": 8, "tags": ["ai"]},
            )
            listed = await client.get("/api/memory/entries?tag=ai", headers=headers)
            searched = await client.get("/api/memory/entries/search?q=searchable", headers=headers)
            extracted = await client.post("/api/memory/extract", headers=headers, json={"days": 30})
            deleted = await client.delete(
                f"/api/memory/entries/{created.json()['id']}", headers=headers
            )
        assert saved.status_code == 200
        assert saved.json()["push_time"] == "08:30"
        assert listed.json()[0]["content"] == "API searchable memory"
        assert searched.json()[0]["content"] == "API searchable memory"
        assert extracted.json() == {"extracted": 0}
        assert deleted.json() == {"status": "deleted"}
    finally:
        await context.close()
