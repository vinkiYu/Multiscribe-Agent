"""Shared initialized FastAPI client for API tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings
from tests.db import get_test_database_url, init_test_database


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Provide an authenticated-test-ready app backed by a clean PostgreSQL database."""
    settings = SystemSettings(_env_file=None, database_url=get_test_database_url())
    database = await init_test_database()
    await database.close()
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
