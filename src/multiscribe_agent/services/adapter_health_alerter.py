"""Fault-isolating publisher notifications for automatically disabled adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import structlog

from multiscribe_agent.core.adapter_health import AdapterHealth
from multiscribe_agent.plugins.registry import PublisherRegistry

log = structlog.get_logger(__name__)


class AdapterHealthAlerter:
    """Send plain-text health alerts through configured publisher targets."""

    def __init__(
        self,
        targets: Sequence[str],
        publisher_options: Mapping[str, Mapping[str, object]],
        publisher_registry: PublisherRegistry | None = None,
    ) -> None:
        """Configure target IDs and their existing publisher options."""
        self._targets = list(dict.fromkeys(target.strip() for target in targets if target.strip()))
        self._publisher_options = dict(publisher_options)
        self._publisher_registry = publisher_registry or PublisherRegistry.get_instance()

    async def alert_disabled(self, adapter_id: str, health: AdapterHealth) -> None:
        """Publish an alert without allowing an unhealthy target to block ingestion."""
        if not self._targets:
            return
        message = (
            "Adapter automatically disabled\n"
            f"Adapter: {adapter_id}\n"
            f"Consecutive failures: {health.consecutive_failures}\n"
            f"Last error: {health.last_error or 'unknown'}\n"
            f"Last run: {health.last_run_at or 'unknown'}\n"
            "Action: inspect the source and manually enable it after repair."
        )
        for target in self._targets:
            try:
                publisher_class = self._publisher_registry.get(target)
                await publisher_class().publish(message, self._publisher_options.get(target))
            except Exception as exc:  # Publisher failures must not stop source collection.
                log.warning(
                    "adapter_health_alert_failed",
                    target=target,
                    adapter_id=adapter_id,
                    error_type=type(exc).__name__,
                )
