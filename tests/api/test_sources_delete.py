"""HTTP coverage for the authenticated sources DELETE endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.api.conftest import auth_headers


@pytest.mark.asyncio
async def test_delete_source_removes_override_and_persists(client: AsyncClient) -> None:
    """A saved source is removed from the live settings and from the override store."""
    headers = await auth_headers(client)
    await client.put(
        "/api/sources/delete-rss",
        headers=headers,
        json={"type": "rss", "config": {"rss_url": "https://example.test/del.xml"}},
    )

    deleted = await client.delete("/api/sources/delete-rss", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "deleted"}

    listed = (await client.get("/api/sources", headers=headers)).json()["sources"]
    assert all(source["id"] != "delete-rss" for source in listed)

    # Reload the service context and confirm the override no longer exists on disk.
    app = client._transport.app  # type: ignore[attr-defined]
    context = app.state.context
    await context.reload()
    reloaded = (await client.get("/api/sources", headers=headers)).json()["sources"]
    assert all(source["id"] != "delete-rss" for source in reloaded)


@pytest.mark.asyncio
async def test_delete_source_returns_404_for_unknown_id(client: AsyncClient) -> None:
    """An unknown source id is rejected with 404 instead of a silent no-op."""
    headers = await auth_headers(client)
    response = await client.delete("/api/sources/never-existed", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "source not found"


@pytest.mark.asyncio
async def test_delete_source_rejects_blank_id(client: AsyncClient) -> None:
    """A whitespace-only id is rejected with 400 before any persistence work."""
    headers = await auth_headers(client)
    response = await client.delete("/api/sources/%20", headers=headers)
    assert response.status_code == 400
    assert "source_id" in response.json()["detail"]
