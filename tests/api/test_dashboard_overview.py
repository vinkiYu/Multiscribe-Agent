from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from multiscribe_agent.agents.workflow.iteration_store import IterationRecord
from multiscribe_agent.infra.repositories.curation_evaluations import CurationEvaluationRecord


async def _auth_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post("/api/login", json={"password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_dashboard_overview_merges_usage_publish_iterations_and_logs(client) -> None:
    assert client is not None
    context = client._transport.app.state.context  # type: ignore[attr-defined]
    assert context.daily_usage is not None
    assert context.db is not None
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    await context.daily_usage.upsert(today, {"total_tokens": 1})
    assert context.iteration_store is not None
    await context.iteration_store.append(
        IterationRecord("run", "step", 1, "out", 8.0, None, True, "threshold")
    )
    assert context.curation_evaluations is not None
    await context.curation_evaluations.upsert(
        CurationEvaluationRecord(
            workflow_run_id="curation-run",
            date=today,
            recorded_at=100,
            rounds=1,
            converged=True,
            exit_reason="threshold",
            final_score=9.0,
            score_delta=None,
            avg_iter_score=9.0,
            result_count=2,
            usage={"total_tokens": 1},
        )
    )
    response = await client.get("/api/dashboard/overview", headers=await _auth_headers(client))
    assert response.status_code == 200
    assert set(response.json()) == {"usage", "publish", "iterations", "evaluation", "task_logs"}
    assert response.json()["usage"]["total_tokens"] == 1
    assert response.json()["iterations"][0]["workflow_run_id"] == "run"
    assert response.json()["evaluation"]["today_summary"]["avg_final_score"] == 9.0


@pytest.mark.asyncio
async def test_dashboard_overview_requires_auth(client) -> None:
    response = await client.get("/api/dashboard/overview")
    assert response.status_code == 401
