"""Tests for the public click tracking redirect."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_track_click_records_and_redirects_without_auth(client: httpx.AsyncClient) -> None:
    """The public endpoint records request metadata and returns the original URL."""
    response = await client.get(
        "/api/track-click",
        params={
            "digest_date": "2026-07-29",
            "item_url": "https://example.test/article?a=1",
            "item_source": "RSS",
            "item_tags": "agent,rag",
        },
        headers={"User-Agent": "test-agent", "Referer": "https://example.test/digest"},
    )
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.test/article?a=1"

    row = await client.get("/healthz")
    assert row.status_code == 200


@pytest.mark.asyncio
async def test_track_click_requires_item_url(client: httpx.AsyncClient) -> None:
    """Missing target URLs produce a client error rather than an open redirect."""
    response = await client.get("/api/track-click", params={"digest_date": "2026-07-29"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_track_click_rejects_non_http_urls(client: httpx.AsyncClient) -> None:
    """The tracker does not become a javascript or file open redirect."""
    response = await client.get(
        "/api/track-click",
        params={"digest_date": "2026-07-29", "item_url": "javascript:alert(1)"},
    )
    assert response.status_code == 400
