"""HTTP tests for the authenticated alert history endpoint."""

from __future__ import annotations

import httpx
import pytest

from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings


@pytest.mark.asyncio
async def test_alert_history_route_lists_persisted_records(tmp_path) -> None:
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "alerts.sqlite"))
    context = ServiceContext(settings)
    await context.init()
    try:
        assert context.alert_history is not None
        record_id = await context.alert_history.record(
            rule_name="errors",
            metric="error_count",
            threshold=0.0,
            value=1.0,
            description="error",
            fired_at=123,
        )
        app = create_app(settings, context)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            unauthorized = await client.get("/api/alerts")
            assert unauthorized.status_code == 401
            login = await client.post("/api/login", json={"password": "admin123"})
            token = login.json()["access_token"]
            response = await client.get(
                "/api/alerts",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
            assert response.json()[0]["id"] == record_id
            assert response.json()[0]["rule_name"] == "errors"
    finally:
        await context.close()
