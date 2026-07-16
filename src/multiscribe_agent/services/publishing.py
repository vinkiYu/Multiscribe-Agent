"""Concurrent fan-out publishing for rendered curated digests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping

import structlog

from multiscribe_agent.plugins.registry import PublisherRegistry
from multiscribe_agent.renderers.models import CuratedDigest

type DigestRenderer = Callable[[CuratedDigest], object]

log = structlog.get_logger(__name__)


class PublishingService:
    """Render a digest per target and isolate target-specific publishing failures."""

    def __init__(
        self,
        publisher_registry: PublisherRegistry,
        renderers: Mapping[str, DigestRenderer],
        publisher_options: Mapping[str, Mapping[str, object]] | None = None,
    ) -> None:
        """Configure injected publisher classes, renderers, and destination options."""
        self._publisher_registry = publisher_registry
        self._renderers = dict(renderers)
        self._publisher_options = dict(publisher_options or {})

    async def fanout(
        self, digest: CuratedDigest, targets: list[str]
    ) -> dict[str, dict[str, object]]:
        """Publish to all targets concurrently without letting one failure stop peers."""
        outcomes = await asyncio.gather(
            *(self._publish_target(digest, target) for target in targets),
            return_exceptions=True,
        )
        results: dict[str, dict[str, object]] = {}
        for target, outcome in zip(targets, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                log.warning(
                    "digest_publish_failed", target=target, error_type=type(outcome).__name__
                )
                results[target] = {"status": "error", "error": str(outcome)}
            else:
                results[target] = outcome
        return results

    async def _publish_target(self, digest: CuratedDigest, target: str) -> dict[str, object]:
        """Render and publish a single target message serially within that target."""
        renderer = self._renderers.get(target)
        if renderer is None:
            raise KeyError(f"no digest renderer configured for target: {target}")
        publisher_class = self._publisher_registry.get(target)
        content = renderer(digest)
        response = await publisher_class().publish(content, self._publisher_options.get(target))
        return {"status": "success", "response": response}
