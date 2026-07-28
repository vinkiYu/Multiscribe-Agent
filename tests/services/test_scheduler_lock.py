"""Unit tests for scheduler lock acquisition and owner-token release."""

from __future__ import annotations

import pytest

from multiscribe_agent.services.scheduler_lock import RedisSchedulerLock


class FakeRedis:
    """Minimal SET NX EX and Lua-release emulator."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def set(self, name: str, value: str, *, ex: int, nx: bool) -> bool | None:
        if nx and name in self.values:
            return None
        self.values[name] = value
        self.ttls[name] = ex
        return True

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> object:
        del script
        assert numkeys == 1
        key, token = keys_and_args
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0


class UnreachableRedis:
    async def set(self, name: str, value: str, *, ex: int, nx: bool) -> bool | None:
        del name, value, ex, nx
        raise ConnectionError("redis unavailable")

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> object:
        del script, numkeys, keys_and_args
        raise AssertionError("release must not be attempted")


@pytest.mark.asyncio
async def test_redis_lock_uses_nx_and_release_only_deletes_own_token() -> None:
    """A busy key is observable and a stale owner cannot delete a new lease."""
    redis = FakeRedis()
    lock = RedisSchedulerLock("redis://unused", client=redis)

    first = await lock.acquire("key", 120)
    second = await lock.acquire("key", 120)
    assert first.acquired is True
    assert first.token is not None
    assert second.acquired is False
    assert second.reason == "already_locked"
    assert redis.ttls["key"] == 120

    await lock.release("key", "stale-token")
    assert "key" in redis.values
    await lock.release("key", first.token)
    assert "key" not in redis.values


@pytest.mark.asyncio
async def test_unconfigured_redis_follows_strict_mode() -> None:
    """Strict mode rejects unavailable Redis while relaxed mode permits fallback."""
    strict = await RedisSchedulerLock("", strict_mode=True).acquire("key", 120)
    relaxed = await RedisSchedulerLock("", strict_mode=False).acquire("key", 120)

    assert strict.unavailable is True
    assert strict.allow_without_lock is False
    assert relaxed.unavailable is True
    assert relaxed.allow_without_lock is True


@pytest.mark.asyncio
async def test_unreachable_redis_is_reported_without_network_retry() -> None:
    """A connection error becomes one deterministic unavailable outcome."""
    result = await RedisSchedulerLock(
        "redis://unused", strict_mode=True, client=UnreachableRedis()
    ).acquire("key", 120)

    assert result.unavailable is True
    assert result.reason == "redis_unreachable"
