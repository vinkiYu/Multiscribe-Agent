"""Agent and workflow CRUD plus SSE endpoint tests."""

import httpx
import pytest

from tests.api.conftest import auth_headers


@pytest.mark.asyncio
async def test_agent_and_workflow_crud(client: httpx.AsyncClient) -> None:
    """Declarative entities can be saved, listed, and deleted through protected routes."""
    headers = await auth_headers(client)
    agent = {
        "id": "a",
        "name": "A",
        "description": "",
        "system_prompt": "x",
        "provider_id": "p",
        "model": "m",
    }
    assert (await client.post("/api/agents", headers=headers, json=agent)).status_code == 200
    assert (await client.get("/api/agents", headers=headers)).json()[0]["id"] == "a"
    workflow = {"id": "w", "name": "W", "description": "", "steps": []}
    assert (await client.post("/api/workflows", headers=headers, json=workflow)).status_code == 200
    assert (await client.delete("/api/agents/a", headers=headers)).status_code == 200
    assert (await client.delete("/api/workflows/w", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_high_risk_tool_approval_endpoint(client: httpx.AsyncClient) -> None:
    """Authenticated users can approve one exact registered high-risk call."""
    headers = await auth_headers(client)
    response = await client.post(
        "/api/agents/tools/approve",
        headers=headers,
        json={
            "tool_call": {
                "id": "call-1",
                "name": "execute_command",
                "arguments": {"command": "git status --short"},
            },
            "ttl_seconds": 60,
        },
    )
    assert response.status_code == 200
    assert response.json()["expires_in"] == 60
    assert isinstance(response.json()["approval_token"], str)
