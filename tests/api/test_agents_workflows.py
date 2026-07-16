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
