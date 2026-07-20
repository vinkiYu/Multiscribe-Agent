"""Regression tests for human-facing API rate limits."""

import httpx
import pytest
from fastapi import FastAPI

from multiscribe_agent.api.middleware import EndpointRateLimiter
from multiscribe_agent.config import SystemSettings


def _app(rules: dict[str, tuple[int, int]]) -> FastAPI:
    app = FastAPI()

    @app.post("/api/login")
    async def login() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/agents/demo/run")
    async def run_agent() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/digest/run")
    async def run_digest() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(EndpointRateLimiter, rules=rules, exempt_paths=("/healthz",))
    return app


@pytest.mark.asyncio
async def test_login_limit_returns_429_and_retry_after() -> None:
    """Login brute-force protection returns the standard retry header."""
    app = _app({"/api/auth/login": (2, 60)})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        responses = [await c.post("/api/login") for _ in range(3)]

    assert [response.status_code for response in responses] == [200, 200, 429]
    assert responses[-1].headers["Retry-After"].isdigit()
    assert responses[-1].json()["retry_after"] >= 1


@pytest.mark.asyncio
async def test_agent_and_digest_rules_are_independent() -> None:
    """Each configured endpoint family maintains its own quota."""
    app = _app({"/api/agents/run": (1, 60), "/api/digest/run": (1, 60)})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        agent_first = await c.post("/api/agents/demo/run")
        agent_second = await c.post("/api/agents/demo/run")
        digest_first = await c.post("/api/digest/run")
        digest_second = await c.post("/api/digest/run")

    assert agent_first.status_code == 200
    assert agent_second.status_code == 429
    assert digest_first.status_code == 200
    assert digest_second.status_code == 429


@pytest.mark.asyncio
async def test_exempt_and_unmatched_paths_are_not_limited() -> None:
    """Health probes and unrelated endpoints bypass the limiter."""
    app = _app({"/api/auth/login": (1, 60)})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        health = await c.get("/healthz")
        missing = await c.get("/does-not-match")

    assert health.status_code == 200
    assert missing.status_code == 404


def test_default_settings_expose_three_human_endpoint_rules() -> None:
    """The default settings expose independent auth, agent, and digest quotas."""
    settings = SystemSettings(_env_file=None)

    assert set(settings.rate_limit.rules) == {
        "/api/auth/login",
        "/api/agents/run",
        "/api/digest/run",
    }


def test_rate_limit_config_rejects_invalid_rules() -> None:
    """Malformed path or non-positive quotas fail during settings validation."""
    with pytest.raises(ValueError, match="rate limit"):
        SystemSettings(_env_file=None, rate_limit={"rules": {"agents/run": (0, 0)}})
