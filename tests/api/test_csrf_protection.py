"""Tests for browser CSRF protection and bearer-token exemption."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from multiscribe_agent.api.middleware.csrf import CsrfMiddleware


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/data")
    async def get_data() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/data")
    async def post_data() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(CsrfMiddleware, exempt_paths=("/api/login",))
    return app


@pytest.mark.asyncio
async def test_form_post_requires_matching_cookie_and_header() -> None:
    """Missing or mismatched tokens return 403 while a matching pair succeeds."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()), base_url="http://test"
    ) as client:
        initial = await client.get("/api/data")
        missing = await client.post("/api/data")
        cookie = client.cookies.get("multiscribe_csrf")
        valid = await client.post("/api/data", headers={"X-CSRF-Token": cookie or ""})

    assert initial.status_code == 200
    assert missing.status_code == 403
    assert valid.status_code == 200


@pytest.mark.asyncio
async def test_bearer_post_is_exempt_from_csrf() -> None:
    """API clients authenticated with a bearer token do not need the browser token."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()), base_url="http://test"
    ) as client:
        response = await client.post("/api/data", headers={"Authorization": "Bearer test"})

    assert response.status_code == 200
