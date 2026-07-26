"""Provider model-catalog synchronization endpoint tests."""

from __future__ import annotations

import httpx
import pytest
import respx

from tests.api.conftest import auth_headers


def _provider(client: httpx.AsyncClient, provider_type: str):
    context = client._transport.app.state.context
    return next(item for item in context.settings.ai_providers if item.type == provider_type)


@pytest.mark.asyncio
@respx.mock
async def test_sync_openai_compatible_models(client: httpx.AsyncClient) -> None:
    provider = _provider(client, "openai")
    provider.base_url = "https://relay.example.test/v1"
    provider.api_key = "sync-secret"
    route = respx.get("https://relay.example.test/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "gpt-b"}, {"id": "gpt-a"}]})
    )

    response = await client.post(
        f"/api/settings/providers/{provider.id}/models", headers=await auth_headers(client), json={}
    )

    assert response.status_code == 200
    assert response.json()["models"] == ["gpt-a", "gpt-b"]
    assert response.json()["source"] == "remote"
    assert route.calls[0].request.headers["Authorization"] == "Bearer sync-secret"


@pytest.mark.asyncio
@respx.mock
async def test_sync_gemini_and_ollama_models(client: httpx.AsyncClient) -> None:
    gemini = _provider(client, "google")
    gemini.base_url = "https://gemini.example.test/v1beta"
    gemini.api_key = "gemini-secret"
    ollama = _provider(client, "ollama")
    ollama.base_url = "http://ollama.example.test"
    respx.get("https://gemini.example.test/v1beta/models").mock(
        return_value=httpx.Response(
            200,
            json={"models": [{"name": "models/gemini-b"}, {"name": "models/gemini-a"}]},
        )
    )
    respx.get("http://ollama.example.test/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "qwen:latest"}]})
    )
    headers = await auth_headers(client)

    gemini_response = await client.post(
        f"/api/settings/providers/{gemini.id}/models", headers=headers, json={}
    )
    ollama_response = await client.post(
        f"/api/settings/providers/{ollama.id}/models", headers=headers, json={}
    )

    assert gemini_response.json()["models"] == ["gemini-a", "gemini-b"]
    assert ollama_response.json()["models"] == ["qwen:latest"]


@pytest.mark.asyncio
@respx.mock
async def test_sync_anthropic_models_uses_remote_catalog(client: httpx.AsyncClient) -> None:
    provider = _provider(client, "anthropic")
    provider.base_url = "https://anthropic.example.test/v1"
    provider.api_key = "anthropic-secret"
    route = respx.get("https://anthropic.example.test/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "claude-test"}]})
    )

    response = await client.post(
        f"/api/settings/providers/{provider.id}/models", headers=await auth_headers(client), json={}
    )

    assert response.status_code == 200
    assert response.json()["source"] == "remote"
    assert response.json()["models"] == ["claude-test"]
    assert route.calls[0].request.headers["x-api-key"] == "anthropic-secret"


@pytest.mark.asyncio
@respx.mock
async def test_provider_connection_test_does_not_persist_draft_credentials(
    client: httpx.AsyncClient,
) -> None:
    provider = _provider(client, "openai")
    route = respx.get("https://draft.example.test/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "draft-model"}]})
    )

    response = await client.post(
        f"/api/settings/providers/{provider.id}/test",
        headers=await auth_headers(client),
        json={"base_url": "https://draft.example.test/v1", "api_key": "draft-secret"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["model_count"] == 1
    assert route.calls[0].request.headers["Authorization"] == "Bearer draft-secret"
    assert provider.base_url != "https://draft.example.test/v1"


@pytest.mark.asyncio
async def test_sync_provider_models_requires_auth(client: httpx.AsyncClient) -> None:
    provider = _provider(client, "openai")

    response = await client.post(f"/api/settings/providers/{provider.id}/models", json={})
    assert response.status_code == 403
