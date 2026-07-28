"""Lazy Redis client lifecycle used by distributed scheduler locks."""

from __future__ import annotations

from redis.asyncio import Redis

_redis: Redis | None = None


def get_redis(redis_url: str | None = None) -> Redis | None:
    """Return the process-local async Redis client for a configured URL.

    Args:
        redis_url: Redis connection URL. Empty or whitespace-only values disable Redis.

    Returns:
        A lazily-created client, or ``None`` when no URL is configured.
    """
    global _redis
    if not redis_url or not redis_url.strip():
        return None
    if _redis is None:
        _redis = Redis.from_url(redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    """Close and clear the process-local Redis client when the app stops."""
    global _redis
    if _redis is None:
        return
    client = _redis
    _redis = None
    await client.aclose()
