"""JWT login and protected-route tests."""

import httpx
import pytest

from tests.api.conftest import auth_headers


@pytest.mark.asyncio
async def test_login_issues_development_token_and_protects_routes(
    client: httpx.AsyncClient,
) -> None:
    """Default password produces must-change token semantics and enables protected access."""
    assert (await client.get("/api/dashboard/stats")).status_code == 401
    response = await client.post("/api/login", json={"password": "admin123"})
    assert response.status_code == 200
    assert response.json()["must_change_password"] is True
    assert (
        await client.get("/api/dashboard/stats", headers=await auth_headers(client))
    ).status_code == 200


@pytest.mark.asyncio
async def test_login_rejects_invalid_password(client: httpx.AsyncClient) -> None:
    """Invalid local password receives an authentication failure."""
    assert (await client.post("/api/login", json={"password": "wrong"})).status_code == 401
