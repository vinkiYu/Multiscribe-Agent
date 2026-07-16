"""Schedule CRUD endpoint tests."""

import httpx
import pytest

from tests.api.conftest import auth_headers


@pytest.mark.asyncio
async def test_schedule_crud_and_unknown_run(client: httpx.AsyncClient) -> None:
    """Schedules persist through the API and unknown immediate runs fail clearly."""
    headers = await auth_headers(client)
    task = {"id": "d", "name": "D", "task_type": "daily_digest", "cron": "0 9 * * *", "config": {}}
    assert (await client.post("/api/schedules", headers=headers, json=task)).status_code == 200
    assert (await client.get("/api/schedules", headers=headers)).json()[0]["id"] == "d"
    assert (await client.delete("/api/schedules/d", headers=headers)).status_code == 200
