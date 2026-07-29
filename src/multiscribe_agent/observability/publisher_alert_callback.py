"""Publisher callback used to deliver operational alert notifications."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import structlog

from multiscribe_agent.plugins.registry import PublisherRegistry

log = structlog.get_logger(__name__)


class PublisherAlertCallback:
    """Fan out concise alert messages while isolating target failures."""

    def __init__(
        self,
        targets: Sequence[str],
        publisher_options: Mapping[str, Mapping[str, object]],
        publisher_registry: PublisherRegistry | None = None,
    ) -> None:
        """Configure publisher IDs, their options, and the registry to use."""
        self._targets = list(dict.fromkeys(target.strip() for target in targets if target.strip()))
        self._publisher_options = dict(publisher_options)
        self._publisher_registry = publisher_registry or PublisherRegistry.get_instance()

    async def __call__(self, rule_name: str, payload: dict[str, object]) -> None:
        """Publish one alert to every configured target without cross-target blocking."""
        if not self._targets:
            return
        message = self._format_message(rule_name, payload)
        for target in self._targets:
            try:
                publisher_class = self._publisher_registry.get(target)
                await publisher_class().publish(message, self._publisher_options.get(target))
            except Exception as exc:  # Alert delivery must not break the alert engine.
                log.warning(
                    "publisher_alert_failed",
                    target=target,
                    rule_name=rule_name,
                    error_type=type(exc).__name__,
                )

    @staticmethod
    def _format_message(rule_name: str, payload: Mapping[str, object]) -> str:
        """Render only non-sensitive alert metadata for external destinations."""
        return "\n".join(
            (
                f"Alert: {rule_name}",
                f"Metric: {payload.get('metric', 'unknown')}",
                f"Threshold: {payload.get('threshold', 'unknown')}",
                f"Description: {payload.get('description', '')}",
                f"Time: {payload.get('timestamp', 'unknown')}",
            )
        )
