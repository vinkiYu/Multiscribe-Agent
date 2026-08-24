"""Regression tests for console settings persistence and environment precedence."""

from __future__ import annotations

import httpx
import pytest

from tests.api.conftest import auth_headers


@pytest.mark.asyncio
async def test_settings_save_survives_environment_layer(client: httpx.AsyncClient) -> None:
    """A console override wins over the process environment and is readable after PUT."""
    headers = await auth_headers(client)
    value = "http://settings.example.test:8123"

    response = await client.put("/api/settings", headers=headers, json={"http_proxy": value})

    assert response.status_code == 200
    assert response.json()["http_proxy"] == value
    reread = await client.get("/api/settings", headers=headers)
    assert reread.status_code == 200
    assert reread.json()["http_proxy"] == value


@pytest.mark.asyncio
async def test_settings_save_merges_masked_provider_secret(client: httpx.AsyncClient) -> None:
    """Saving a masked API key keeps the existing secret while updating its endpoint."""
    headers = await auth_headers(client)
    settings = (await client.get("/api/settings", headers=headers)).json()
    provider = next(item for item in settings["ai_providers"] if item["type"] == "openai")
    provider["api_key"] = "test-secret"
    seeded = await client.put("/api/settings", headers=headers, json={"ai_providers": [provider]})
    assert seeded.status_code == 200
    provider["base_url"] = "https://relay.example.test/v1"
    provider["api_key"] = "********"

    response = await client.put("/api/settings", headers=headers, json={"ai_providers": [provider]})

    assert response.status_code == 200
    saved = next(item for item in response.json()["ai_providers"] if item["id"] == provider["id"])
    assert saved["base_url"] == "https://relay.example.test/v1"
    assert saved["api_key"] == "********"
