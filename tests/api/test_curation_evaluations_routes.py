from __future__ import annotations

import pytest
from httpx import AsyncClient

from multiscribe_agent.infra.repositories.curation_evaluations import CurationEvaluationRecord


async def _auth_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post("/api/login", json={"password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_curation_evaluation_routes_are_authenticated_and_aggregate(
    client: AsyncClient,
) -> None:
    context = client._transport.app.state.context  # type: ignore[attr-defined]
    assert context.curation_evaluations is not None
    await context.curation_evaluations.upsert(
        CurationEvaluationRecord(
            workflow_run_id="run-1",
            date="2026-07-29",
            recorded_at=100,
            rounds=1,
            converged=True,
            exit_reason="threshold",
            final_score=9.0,
            score_delta=None,
            avg_iter_score=9.0,
            result_count=3,
            usage={"total_tokens": 12},
        )
    )
    headers = await _auth_headers(client)
    listed = await client.get("/api/curation-evaluations", headers=headers)
    summary = await client.get("/api/curation-evaluations/summary", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["workflow_run_id"] == "run-1"
    assert summary.status_code == 200
    assert summary.json()["total_runs"] == 1


@pytest.mark.asyncio
async def test_curation_evaluation_routes_reject_anonymous_requests(client: AsyncClient) -> None:
    assert (await client.get("/api/curation-evaluations")).status_code == 401
    assert (await client.get("/api/curation-evaluations/summary")).status_code == 401
