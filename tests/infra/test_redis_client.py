"""Tests for lazy Redis client lifecycle without a live Redis server."""

from __future__ import annotations

import pytest

import multiscribe_agent.infra.redis_client as redis_client_module


def test_get_redis_returns_none_for_empty_url(monkeypatch) -> None:
    """An explicitly empty URL disables the optional Redis integration."""
    monkeypatch.setattr(redis_client_module, "_redis", None)

    assert redis_client_module.get_redis("") is None
    assert redis_client_module.get_redis("  ") is None


def test_get_redis_is_lazy_and_reuses_one_client(monkeypatch) -> None:
    """Constructing a client does not contact Redis and reuses the singleton."""
    monkeypatch.setattr(redis_client_module, "_redis", None)

    first = redis_client_module.get_redis("redis://localhost:6379/0")
    second = redis_client_module.get_redis("redis://other-host:6379/1")

    assert first is not None
    assert second is first


@pytest.mark.asyncio
async def test_close_redis_clears_the_singleton(monkeypatch) -> None:
    """Application shutdown closes the client and permits a later fresh client."""

    class FakeRedis:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    fake = FakeRedis()
    monkeypatch.setattr(redis_client_module, "_redis", fake)

    await redis_client_module.close_redis()

    assert fake.closed is True
    assert redis_client_module._redis is None
