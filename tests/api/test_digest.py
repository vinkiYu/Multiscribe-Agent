"""Manual digest trigger tests."""

import httpx
import pytest

from tests.api.conftest import auth_headers


@pytest.mark.asyncio
async def test_digest_run_requires_configured_curator(client: httpx.AsyncClient) -> None:
    """Digest trigger returns a useful validation error when its curator is not stored."""
    response = await client.post(
        "/api/digest/run", headers=await auth_headers(client), json={"curate_agent_id": "missing"}
    )
    assert response.status_code == 400
