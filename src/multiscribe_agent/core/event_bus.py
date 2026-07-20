"""Lightweight async in-process event bus with isolated subscriber failures."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from threading import RLock

log = logging.getLogger(__name__)

type EventPayload = dict[str, object]
type AsyncSubscriber = Callable[[EventPayload], Awaitable[None]]


@dataclass
class EventBus:
    """Publish/subscribe bus with thread-safe registration and failure isolation."""

    _subscribers: dict[str, list[AsyncSubscriber]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def subscribe(self, topic: str, callback: AsyncSubscriber) -> None:
        """Register an async subscriber for a topic."""
        with self._lock:
            self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: AsyncSubscriber) -> None:
        """Remove a previously registered subscriber; missing callbacks are ignored."""
        with self._lock:
            try:
                self._subscribers[topic].remove(callback)
            except ValueError:
                return

    async def publish(self, topic: str, payload: EventPayload) -> None:
        """Notify a snapshot of subscribers without propagating subscriber failures."""
        with self._lock:
            subscribers = tuple(self._subscribers.get(topic, ()))
        if not subscribers:
            return
        results = await asyncio.gather(
            *(self._safe_call(subscriber, topic, payload) for subscriber in subscribers),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                log.warning("event_bus_subscriber_failed", extra={"topic": topic})

    async def _safe_call(
        self, subscriber: AsyncSubscriber, topic: str, payload: EventPayload
    ) -> None:
        try:
            await subscriber(payload)
        except Exception as exc:
            log.warning(
                "event_bus_subscriber_error",
                extra={
                    "topic": topic,
                    "subscriber": getattr(subscriber, "__name__", "?"),
                    "error_type": type(exc).__name__,
                },
            )
            raise

    def clear(self) -> None:
        """Remove all subscribers, primarily for test isolation."""
        with self._lock:
            self._subscribers.clear()


_event_bus: EventBus | None = None
_event_bus_lock = RLock()


def get_event_bus() -> EventBus:
    """Return the process-wide lazily initialized event bus."""
    global _event_bus
    with _event_bus_lock:
        if _event_bus is None:
            _event_bus = EventBus()
        return _event_bus


def set_event_bus(bus: EventBus) -> None:
    """Replace the process-wide event bus, useful for application/test composition."""
    global _event_bus
    with _event_bus_lock:
        _event_bus = bus
