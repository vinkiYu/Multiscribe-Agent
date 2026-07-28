from __future__ import annotations

import httpx
import pytest

from tests.api.conftest import auth_headers


@pytest.mark.asyncio
async def test_adapter_health_list_and_manual_enable_disable(client: httpx.AsyncClient) -> None:
    """Operators can inspect health and recover a source through the authenticated API."""
    headers = await auth_headers(client)

    assert (await client.get("/api/adapter-health", headers=headers)).json() == []

    disabled = await client.post(
        "/api/adapter-health/rss-adapter/disable",
        headers=headers,
    )
    assert disabled.status_code == 200
    assert disabled.json()["adapter_id"] == "rss-adapter"
    assert disabled.json()["disabled"] is True

    listed = await client.get("/api/adapter-health", headers=headers)
    assert listed.status_code == 200
    assert listed.json() == [disabled.json()]

    enabled = await client.post(
        "/api/adapter-health/rss-adapter/enable",
        headers=headers,
    )
    assert enabled.status_code == 200
    assert enabled.json()["disabled"] is False
    assert enabled.json()["consecutive_failures"] == 0


@pytest.mark.asyncio
async def test_adapter_health_routes_require_authentication(client: httpx.AsyncClient) -> None:
    """Health controls are not exposed without the existing console authentication."""
    assert (await client.get("/api/adapter-health")).status_code == 401
    assert (await client.post("/api/adapter-health/rss/disable")).status_code == 403
