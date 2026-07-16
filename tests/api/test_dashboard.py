"""Dashboard endpoint tests."""

import httpx
import pytest

from tests.api.conftest import auth_headers


@pytest.mark.asyncio
async def test_dashboard_stats_logs_and_invalid_ingest(client: httpx.AsyncClient) -> None:
    """Dashboard responses have stable shape and validate manual ingestion payloads."""
    headers = await auth_headers(client)
    assert (await client.get("/api/dashboard/stats", headers=headers)).json()["source_count"] == 0
    assert (await client.get("/api/dashboard/logs", headers=headers)).json() == []
    assert (
        await client.post(
            "/api/dashboard/ingest", headers=headers, json={"adapter_configs": "invalid"}
        )
    ).status_code == 400
