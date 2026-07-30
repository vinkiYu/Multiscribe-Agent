"""HTTP coverage for authenticated source-data FTS search."""

from __future__ import annotations

from httpx import AsyncClient

from multiscribe_agent.domain.models import UnifiedData


async def _auth_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post("/api/login", json={"password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_source_data_search_returns_highlighted_results(client: AsyncClient) -> None:
    context = client._transport.app.state.context  # type: ignore[attr-defined]
    assert context.source_data is not None
    await context.source_data.save_batch(
        [
            UnifiedData(
                id="source-1",
                title="AI agent release",
                url="https://example.com/source-1",
                description="A practical AI agent engineering update.",
                published_date="2026-07-30",
                ingestion_date="2026-07-30",
                source="rss",
                category="ai",
                metadata={},
            )
        ],
        "rss-adapter",
    )
    headers = await _auth_headers(client)
    response = await client.get(
        "/api/source-data/search", params={"q": "AI", "limit": 20}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()[0]["id"] == "source-1"
    assert "<mark>" in response.json()[0]["description"]
    assert response.json()[0]["adapter_name"] == "rss-adapter"


async def test_source_data_search_handles_empty_and_invalid_fts_queries(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)
    empty = await client.get("/api/source-data/search", params={"q": "   "}, headers=headers)
    invalid = await client.get("/api/source-data/search", params={"q": '"'}, headers=headers)
    assert empty.status_code == 400
    assert invalid.status_code == 200
    assert invalid.json() == []


async def test_source_data_search_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/source-data/search", params={"q": "AI"})
    assert response.status_code == 401
