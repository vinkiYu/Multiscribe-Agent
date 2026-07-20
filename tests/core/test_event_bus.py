"""Tests for the in-process domain EventBus."""

from __future__ import annotations

import asyncio

import pytest

from multiscribe_agent.core.event_bus import EventBus


@pytest.mark.asyncio
async def test_publish_delivers_payload_and_isolates_subscriber_errors() -> None:
    """One failing subscriber must not prevent another from receiving the event."""
    bus = EventBus()
    received: list[dict[str, object]] = []

    async def failing(_: dict[str, object]) -> None:
        raise RuntimeError("subscriber failed")

    async def working(payload: dict[str, object]) -> None:
        received.append(payload)

    bus.subscribe("digest.completed", failing)
    bus.subscribe("digest.completed", working)

    await bus.publish("digest.completed", {"item_count": 3})

    assert received == [{"item_count": 3}]


@pytest.mark.asyncio
async def test_registration_is_thread_safe_and_unsubscribe_isolated() -> None:
    """Concurrent registration and removal leave only active subscribers."""
    bus = EventBus()
    calls = 0
    calls_lock = asyncio.Lock()

    async def subscriber(_: dict[str, object]) -> None:
        nonlocal calls
        async with calls_lock:
            calls += 1

    await asyncio.gather(
        *(asyncio.to_thread(bus.subscribe, "topic", subscriber) for _ in range(10))
    )
    bus.unsubscribe("topic", subscriber)
    await bus.publish("topic", {})

    assert calls == 9
