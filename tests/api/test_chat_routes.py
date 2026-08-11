"""API tests for the chat endpoints and the SYSTEM_PASSWORD bypass path."""

from __future__ import annotations

import httpx
import pytest

from multiscribe_agent.api.security import (
    get_current_user,
    get_optional_user,
)


@pytest.mark.asyncio
async def test_chat_routes_require_admin_when_system_password_is_set(
    client: httpx.AsyncClient,
) -> None:
    """A configured system password forces bearer authentication for chat routes."""
    app = client._transport.app  # type: ignore[attr-defined]
    app.state.settings.system_password = "set-for-test"
    response = await client.get("/api/chat/sessions")
    assert response.status_code == 401
    login = await client.post("/api/login", json={"password": "admin123"})
    assert login.status_code == 401
    # The /api/login route refuses to authenticate because the expected password
    # changed; the only safe path now is to construct a JWT manually using the
    # development secret. Falling back to the X-Admin-Bypass path is invalid
    # here because system_password is set.
    from jose import jwt

    token = jwt.encode(
        {"sub": "admin", "role": "admin", "iat": 0, "exp": 9_999_999_999},
        "multiscribe-development-jwt-secret",
        algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post("/api/chat/sessions", json={"title": "笔记"}, headers=headers)
    assert created.status_code == 200
    session_id = created.json()["id"]

    listed = await client.get("/api/chat/sessions", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == session_id for item in listed.json())

    sent = await client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "你好"},
        headers=headers,
    )
    assert sent.status_code == 200
    assert sent.json()["role"] == "assistant"

    fetched = await client.get(f"/api/chat/sessions/{session_id}/messages", headers=headers)
    assert fetched.status_code == 200
    assert [item["role"] for item in fetched.json()] == ["user", "assistant"]

    deleted = await client.delete(f"/api/chat/sessions/{session_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "deleted"}


@pytest.mark.asyncio
async def test_chat_bypass_header_allows_admin_when_password_unset(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """X-Admin-Bypass: 1 lets a single-user deployment use chat without a password."""
    # The default settings already use an empty system_password; assert the assumption
    # and ensure the test only runs in a single-user configuration.
    app = client._transport.app  # type: ignore[attr-defined]
    assert not app.state.settings.system_password, "test assumes system_password is unset"
    app.state.settings.system_password = ""

    headers = {"X-Admin-Bypass": "1"}
    created = await client.post("/api/chat/sessions", json={"title": "bypass"}, headers=headers)
    assert created.status_code == 200
    session_id = created.json()["id"]

    sent = await client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "hi"},
        headers=headers,
    )
    assert sent.status_code == 200
    assert sent.json()["role"] == "assistant"

    # Without the bypass header the same request must be rejected. CSRF
    # middleware returns 403 for state-changing requests without a token.
    forbidden = await client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "no bypass"},
    )
    assert forbidden.status_code in (401, 403)


# Silence unused-import warning for the get_current_user alias from chat_routes tests.
_ = get_current_user


@pytest.mark.asyncio
async def test_optional_user_dependency_handles_missing_token() -> None:
    """get_optional_user returns None when no bearer token is provided and no bypass applies."""

    class _StubRequest:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

    class _Settings:
        system_password = "set"
        jwt_secret = "test-secret"

    class _StubApp:
        state = type("State", (), {"settings": _Settings()})()

    request = _StubRequest()
    request.app = _StubApp()
    assert await get_optional_user(request) is None

    # Setting system_password to empty allows the X-Admin-Bypass header to authenticate.
    request.headers["X-Admin-Bypass"] = "1"
    _Settings.system_password = ""
    user = await get_optional_user(request)
    assert user == {"sub": "admin", "role": "admin", "must_change_password": True}


@pytest.mark.asyncio
async def test_chat_messages_route_404_for_unknown_session(
    client: httpx.AsyncClient,
) -> None:
    """Posting a message to a missing session returns 404."""
    login = await client.post("/api/login", json={"password": "admin123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = await client.post(
        "/api/chat/sessions/missing-id/messages",
        json={"content": "hi"},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_chat_send_message_uses_bound_executor_reply(
    client: httpx.AsyncClient,
) -> None:
    """Once bootstrap binds the chat executor, /messages returns the runner's content."""
    from multiscribe_agent.bootstrap import _ChatAgentRunner
    from multiscribe_agent.services.chat_service import (
        _UNBOUND_PLACEHOLDER,
        ChatService,
    )

    headers = {"X-Admin-Bypass": "1"}
    created = await client.post("/api/chat/sessions", json={"title": "binding"}, headers=headers)
    assert created.status_code == 200
    session_id = created.json()["id"]

    app = client._transport.app  # type: ignore[attr-defined]
    context = app.state.context
    assert isinstance(context.chat_service, ChatService)
    runner = context.chat_service._agent_runner
    assert isinstance(runner, _ChatAgentRunner)

    original_run = runner.run  # type: ignore[attr-defined]

    async def fake_run(agent_def: object, user_input: str) -> str:
        return f"echo:{user_input}"

    runner.run = fake_run  # type: ignore[method-assign, attr-defined]
    try:
        sent = await client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"content": "hello"},
            headers=headers,
        )
        assert sent.status_code == 200
        body = sent.json()
        assert body["role"] == "assistant"
        assert body["content"] == "echo:hello"
        assert body["content"] != _UNBOUND_PLACEHOLDER
    finally:
        runner.run = original_run  # type: ignore[method-assign, attr-defined]
