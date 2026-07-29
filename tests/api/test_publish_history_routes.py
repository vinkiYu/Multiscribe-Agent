from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _auth_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post("/api/login", json={"password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_publish_history_summary_returns_aggregates(client: AsyncClient) -> None:
    context = client._transport.app.state.context  # type: ignore[attr-defined]
    assert context.db is not None
    assert context.publish_history is not None
    await context.publish_history.add(context.db, "feishu", "success", "ok", "body", {})
    await context.publish_history.add(context.db, "wecom", "error", "failed", "body", {})

    response = await client.get("/api/publish-history/summary", headers=await _auth_headers(client))

    assert response.status_code == 200
    assert response.json() == {"total": 2, "success": 1, "error": 1}


@pytest.mark.asyncio
async def test_publish_history_summary_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/publish-history/summary")
    assert response.status_code == 401
