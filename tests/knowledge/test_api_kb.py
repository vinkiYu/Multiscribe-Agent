"""Authenticated API coverage for P16 knowledge-base operations."""

from __future__ import annotations

import httpx
import pytest

from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings


@pytest.mark.asyncio
async def test_kb_api_requires_auth_and_supports_core_workflow(tmp_path) -> None:
    """JWT-protected endpoints expose degraded capabilities and FTS CRUD."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "kb.sqlite"))
    context = ServiceContext(settings)
    await context.init()
    try:
        app = create_app(settings, context)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/kb/capabilities")).status_code == 401
            login = await client.post("/api/login", json={"password": "admin123"})
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            capabilities = await client.get("/api/kb/capabilities", headers=headers)
            category = await client.post(
                "/api/kb/categories", headers=headers, json={"name": "API"}
            )
            category_id = category.json()["id"]
            document = await client.post(
                "/api/kb/documents/text",
                headers=headers,
                json={
                    "text": "API knowledge retrieval",
                    "category_id": category_id,
                    "name": "API note",
                },
            )
            search = await client.get("/api/kb/search?q=retrieval", headers=headers)
            deleted = await client.delete(
                f"/api/kb/documents/{document.json()['id']}", headers=headers
            )

        assert capabilities.status_code == 200
        assert capabilities.json()["fts"] is True
        assert document.status_code == 200
        assert search.json()["hits"][0]["content"] == "API knowledge retrieval"
        assert deleted.json() == {"status": "deleted"}
    finally:
        await context.close()
