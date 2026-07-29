"""Tests for the authenticated Workflow Loop iteration read API."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from multiscribe_agent.agents.workflow.iteration_store import IterationRecord
from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings


async def _app_with_iterations(
    tmp_path: Path,
) -> tuple[httpx.AsyncClient, ServiceContext]:
    """Create an initialized test app with two persisted run histories."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "workflow.sqlite"))
    context = ServiceContext(settings)
    await context.init()
    assert context.iteration_store is not None
    await context.iteration_store.append(
        IterationRecord("run-a", "loop", 1, "draft", 6.0, "add detail", False, "retry")
    )
    await context.iteration_store.append(
        IterationRecord("run-a", "loop", 2, "final", 9.0, None, True, "threshold")
    )
    await context.iteration_store.append(
        IterationRecord("run-b", "other", 1, "other", 8.0, None, True, "threshold")
    )
    app = create_app(settings, context)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return client, context


@pytest.mark.asyncio
async def test_workflow_iterations_route_filters_run_and_step(tmp_path) -> None:
    """The run+step query returns ordered records and score deltas."""
    client, context = await _app_with_iterations(tmp_path)
    try:
        login = await client.post("/api/login", json={"password": "admin123"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        response = await client.get(
            "/api/workflow-iterations",
            params={"run_id": "run-a", "step_id": "loop"},
            headers=headers,
        )
        assert response.status_code == 200
        assert [item["round"] for item in response.json()] == [1, 2]
        assert response.json()[1]["delta"] == 3.0
        assert response.json()[1]["reason"] == "threshold"
    finally:
        await client.aclose()
        await context.close()


@pytest.mark.asyncio
async def test_workflow_iterations_route_lists_recent_and_requires_auth(tmp_path) -> None:
    """The dashboard query spans runs, applies limit, and is protected."""
    client, context = await _app_with_iterations(tmp_path)
    try:
        unauthorized = await client.get("/api/workflow-iterations")
        assert unauthorized.status_code == 401
        login = await client.post("/api/login", json={"password": "admin123"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        response = await client.get(
            "/api/workflow-iterations", params={"limit": 2}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()) == 2
        assert {item["workflow_run_id"] for item in response.json()} <= {"run-a", "run-b"}
    finally:
        await client.aclose()
        await context.close()
