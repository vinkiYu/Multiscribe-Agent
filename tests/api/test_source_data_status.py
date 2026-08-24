"""HTTP coverage for source-data batch status update and update_status repo method."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from multiscribe_agent.domain.models import UnifiedData


async def _auth_headers(client: AsyncClient) -> dict[str, str]:
    """Log in using the documented development password."""
    response = await client.post("/api/login", json={"password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _seed_three_rows(client: AsyncClient) -> None:
    """Insert three source-data rows that share the 'rss' source for status transitions."""
    context = client._transport.app.state.context  # type: ignore[attr-defined]
    assert context.source_data is not None
    await context.source_data.save_batch(
        [
            UnifiedData(
                id=f"status-row-{index}",
                title=f"Status row {index}",
                url=f"https://example.com/status-row-{index}",
                description=f"Status transition fixture {index}",
                published_date="2026-07-30",
                ingestion_date="2026-07-30",
                source="rss",
                category="ai",
                metadata={},
            )
            for index in range(3)
        ],
        "rss-adapter",
    )


async def test_source_data_batch_status_updates_rows(client: AsyncClient) -> None:
    """A 200 response returns the requested status, updated count, and ids list."""
    await _seed_three_rows(client)
    headers = await _auth_headers(client)
    response = await client.post(
        "/api/source-data/batch-status",
        json={"ids": ["status-row-0", "status-row-1"], "status": "curated"},
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "curated"
    assert payload["updated"] == 2
    assert sorted(payload["ids"]) == ["status-row-0", "status-row-1"]


async def test_source_data_batch_status_rejects_empty_ids(client: AsyncClient) -> None:
    """An empty ids list is rejected with 400."""
    headers = await _auth_headers(client)
    response = await client.post(
        "/api/source-data/batch-status",
        json={"ids": [], "status": "curated"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "ids" in response.json()["detail"]


async def test_source_data_batch_status_rejects_invalid_status(client: AsyncClient) -> None:
    """An unrecognized status is rejected with 400 and lists the valid options."""
    headers = await _auth_headers(client)
    response = await client.post(
        "/api/source-data/batch-status",
        json={"ids": ["status-row-0"], "status": "banana"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "curated" in response.json()["detail"]


async def test_source_data_batch_status_rejects_non_string_ids(client: AsyncClient) -> None:
    """A payload with non-string entries is rejected with 400."""
    headers = await _auth_headers(client)
    response = await client.post(
        "/api/source-data/batch-status",
        json={"ids": ["status-row-0", 42], "status": "curated"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "ids" in response.json()["detail"]


@pytest.mark.asyncio
async def test_source_data_repository_update_status_returns_row_count() -> None:
    """The repository method returns the number of rows that changed."""
    from multiscribe_agent.infra.db import init_db
    from multiscribe_agent.infra.repositories.source_data import SourceDataRepository

    db = await init_db(":memory:")
    try:
        repo = SourceDataRepository(db)
        await repo.save_batch(
            [
                UnifiedData(
                    id=f"repo-row-{index}",
                    title=f"Repo row {index}",
                    url=f"https://example.com/repo-row-{index}",
                    description=f"Repository fixture {index}",
                    published_date="2026-07-30",
                    ingestion_date="2026-07-30",
                    source="rss",
                    category="ai",
                    metadata={},
                )
                for index in range(2)
            ],
            "rss-adapter",
        )
        assert await repo.update_status(["repo-row-0"], "curated") == 1
        # Re-applying the same status is still a write at the SQL level.
        assert await repo.update_status(["repo-row-0", "repo-row-1"], "ignored") == 2
        # Empty ids is a no-op.
        assert await repo.update_status([], "curated") == 0
    finally:
        await db.close()
