"""Tests for digest multi-target publishing orchestration."""

from __future__ import annotations

import asyncio
from typing import ClassVar

import pytest

from multiscribe_agent.renderers.feishu_card import DigestItem
from multiscribe_agent.renderers.models import CuratedDigest
from multiscribe_agent.services.publishing import PublishingService


class PublisherRegistry:
    """Minimal registry returning preconfigured publisher classes."""

    def __init__(self, entries: dict[str, type[object]]) -> None:
        self._entries = entries

    def get(self, target: str) -> type[object]:
        """Return a publisher class for a target."""
        return self._entries[target]


class SuccessfulPublisher:
    """Record one successful target delivery."""

    calls: ClassVar[list[object]] = []

    async def publish(self, content: object, options: object = None) -> dict[str, object]:
        """Delay briefly to prove that target fan-out may overlap."""
        del options
        await asyncio.sleep(0.01)
        self.calls.append(content)
        return {"delivered": True}


class FailingPublisher:
    """Model an isolated destination delivery failure."""

    async def publish(self, content: object, options: object = None) -> dict[str, object]:
        """Raise after accepting rendered content."""
        del content, options
        raise RuntimeError("target unavailable")


def _digest() -> CuratedDigest:
    """Build a minimal publishable digest."""
    return CuratedDigest(
        date="2026-07-17",
        title="Daily",
        items=[DigestItem("Item", "Summary", "https://example.test", "RSS", 9.0)],
    )


@pytest.mark.asyncio
async def test_fanout_isolates_target_failure_and_returns_per_target_status() -> None:
    """One failing publisher must not stop a concurrently scheduled successful peer."""
    SuccessfulPublisher.calls = []
    service = PublishingService(
        PublisherRegistry({"good": SuccessfulPublisher, "bad": FailingPublisher}),  # type: ignore[arg-type]
        {
            "good": lambda digest: f"good:{digest.title}",
            "bad": lambda digest: f"bad:{digest.title}",
        },
    )

    results = await service.fanout(_digest(), ["good", "bad"])

    assert results["good"] == {"status": "success", "response": {"delivered": True}}
    assert results["bad"] == {"status": "error", "error": "target unavailable"}
    assert SuccessfulPublisher.calls == ["good:Daily"]
