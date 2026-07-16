"""Shared initialized FastAPI client for API tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings


@pytest.fixture
async def client(tmp_path) -> AsyncIterator[httpx.AsyncClient]:
    """Provide an authenticated-test-ready app backed by a temporary SQLite database."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "api.sqlite"))
    context = ServiceContext(settings)
    await context.init()
    app = create_app(settings, context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as api_client:
        yield api_client
    await context.close()


async def auth_headers(client: httpx.AsyncClient) -> dict[str, str]:
    """Log in using the documented development password."""
    response = await client.post("/api/login", json={"password": "admin123"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
