"""Distributed lock implementations for scheduled task execution."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import uuid4

import structlog
from redis.exceptions import RedisError

from multiscribe_agent.infra.redis_client import get_redis

log = structlog.get_logger(__name__)

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


@dataclass(frozen=True, slots=True)
class AcquireResult:
    """Outcome of one lock acquisition attempt."""

    acquired: bool
    token: str | None = None
    reason: str = ""
    unavailable: bool = False
    allow_without_lock: bool = False


class SchedulerLock(Protocol):
    """Async lock boundary shared by Redis and test implementations."""

    async def acquire(self, key: str, ttl_seconds: int) -> AcquireResult:
        """Try to acquire a lease for a scheduled task."""

    async def release(self, key: str, token: str) -> None:
        """Release a lease only when its owner token still matches."""


class RedisLockClient(Protocol):
    """Minimal Redis command surface needed by ``RedisSchedulerLock``."""

    async def set(
        self,
        name: str,
        value: str,
        ex: int,
        nx: bool,
    ) -> bool | None:
        """Set a lease only when the key does not already exist."""

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> object:
        """Execute the owner-token release script."""


class RedisSchedulerLock:
    """Acquire scheduler leases in Redis with safe owner-token release."""

    def __init__(
        self,
        redis_url: str,
        *,
        strict_mode: bool = True,
        client: RedisLockClient | None = None,
    ) -> None:
        """Configure a lazy Redis lock without making a network call."""
        self._redis_url = redis_url
        self.strict_mode = strict_mode
        self._client = client

    async def acquire(self, key: str, ttl_seconds: int) -> AcquireResult:
        """Atomically acquire a lease or return an observable unavailable result."""
        if ttl_seconds <= 0:
            raise ValueError("scheduler lock TTL must be positive")
        client = self._client or get_redis(self._redis_url)
        if client is None:
            return AcquireResult(
                acquired=False,
                reason="redis_not_configured",
                unavailable=True,
                allow_without_lock=not self.strict_mode,
            )
        token = uuid4().hex
        try:
            acquired = await client.set(key, token, ex=ttl_seconds, nx=True)
        except (RedisError, OSError, TimeoutError) as exc:
            log.warning(
                "scheduler_lock_unavailable",
                error_type=type(exc).__name__,
                strict_mode=self.strict_mode,
            )
            return AcquireResult(
                acquired=False,
                reason="redis_unreachable",
                unavailable=True,
                allow_without_lock=not self.strict_mode,
            )
        if acquired:
            return AcquireResult(acquired=True, token=token, reason="acquired")
        return AcquireResult(acquired=False, reason="already_locked")

    async def release(self, key: str, token: str) -> None:
        """Delete the lease only if Redis still contains this owner's token."""
        client = self._client or get_redis(self._redis_url)
        if client is None:
            return
        try:
            result = client.eval(_RELEASE_SCRIPT, 1, key, token)
            await cast(Awaitable[object], result)
        except (RedisError, OSError, TimeoutError) as exc:
            log.warning(
                "scheduler_lock_release_failed",
                error_type=type(exc).__name__,
            )


class NoOpSchedulerLock:
    """In-process lock adapter used when SchedulerService is constructed directly."""

    async def acquire(self, key: str, ttl_seconds: int) -> AcquireResult:
        """Always grant a local lease for backwards-compatible unit tests."""
        del key
        if ttl_seconds <= 0:
            raise ValueError("scheduler lock TTL must be positive")
        return AcquireResult(acquired=True, token=uuid4().hex, reason="noop")

    async def release(self, key: str, token: str) -> None:
        """Release a local lease, which has no external state."""
        del key, token
