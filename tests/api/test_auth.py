"""JWT login and protected-route tests."""

import httpx
import pytest
from jose import jwt  # type: ignore[import-untyped]

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


@pytest.mark.asyncio
async def test_login_uses_configured_console_session_duration(
    client: httpx.AsyncClient,
) -> None:
    """The local console session duration is read from the active settings."""
    client._transport.app.state.settings.console_session_hours = 48  # type: ignore[attr-defined]
    response = await client.post("/api/login", json={"password": "admin123"})

    assert response.status_code == 200
    payload = jwt.get_unverified_claims(response.json()["access_token"])
    assert int(payload["exp"]) - int(payload["iat"]) == 48 * 60 * 60
