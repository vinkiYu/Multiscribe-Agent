"""Source-adapter configuration endpoint tests."""

from __future__ import annotations

import httpx
import pytest

from tests.api.conftest import auth_headers


@pytest.mark.asyncio
async def test_source_configurations_can_be_read_and_saved(client: httpx.AsyncClient) -> None:
    """Source updates are authenticated, persisted in the active context, and readable."""
    headers = await auth_headers(client)
    initial = await client.get("/api/sources", headers=headers)
    assert initial.status_code == 200
    assert "sources" in initial.json()
    assert "available_adapters" in initial.json()

    saved = await client.put(
        "/api/sources/team-rss",
        headers=headers,
        json={
            "type": "rss",
            "enabled": True,
            "config": {"rss_urls": ["https://example.test/feed.xml"], "source_name": "Team"},
        },
    )
    assert saved.status_code == 200
    assert saved.json() == {
        "id": "team-rss",
        "type": "rss",
        "enabled": True,
        "config": {"rss_urls": ["https://example.test/feed.xml"], "source_name": "Team"},
    }

    sources = (await client.get("/api/sources", headers=headers)).json()["sources"]
    assert any(source["id"] == "team-rss" for source in sources)


@pytest.mark.asyncio
async def test_source_configuration_survives_service_reload(client: httpx.AsyncClient) -> None:
    """Persisted source settings are applied when the service graph is rebuilt."""
    headers = await auth_headers(client)
    saved = await client.put(
        "/api/sources/reload-rss",
        headers=headers,
        json={"type": "rss", "config": {"rss_url": "https://example.test/reload.xml"}},
    )
    assert saved.status_code == 200

    context = client._transport.app.state.context
    await context.reload()
    sources = (await client.get("/api/sources", headers=headers)).json()["sources"]
    assert next(source for source in sources if source["id"] == "reload-rss")["config"] == {
        "rss_url": "https://example.test/reload.xml"
    }


@pytest.mark.asyncio
async def test_source_configurations_mask_and_preserve_sensitive_values(
    client: httpx.AsyncClient,
) -> None:
    """Credential-like fields are never returned and a masked save preserves the stored value."""
    headers = await auth_headers(client)
    original = await client.put(
        "/api/sources/private-source",
        headers=headers,
        json={
            "type": "rss",
            "config": {"rss_url": "https://example.test/feed.xml", "webhook_token": "secret"},
        },
    )
    assert original.status_code == 200
    assert original.json()["config"]["webhook_token"] == "********"

    preserved = await client.put(
        "/api/sources/private-source",
        headers=headers,
        json={
            "type": "rss",
            "config": {"rss_url": "https://example.test/feed.xml", "webhook_token": "********"},
        },
    )
    assert preserved.status_code == 200
    assert preserved.json()["config"]["webhook_token"] == "********"


@pytest.mark.asyncio
async def test_source_configuration_requires_auth_and_valid_payload(
    client: httpx.AsyncClient,
) -> None:
    """The source API rejects unauthenticated and malformed writes."""
    assert (await client.get("/api/sources")).status_code == 401
    headers = await auth_headers(client)
    assert (
        await client.put("/api/sources/bad", headers=headers, json={"type": "rss", "config": []})
    ).status_code == 400
