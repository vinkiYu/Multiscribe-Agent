"""Explicitly enabled notifications for evaluation regression gates (P64.3 T14)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import structlog

from multiscribe_agent.eval.benchmark import RegressionDetected
from multiscribe_agent.plugins.registry import PublisherRegistry

log = structlog.get_logger(__name__)


class RegressionNotifier:
    """Publish concise regression metadata only when explicit targets are configured."""

    def __init__(
        self,
        targets: Sequence[str] = (),
        publisher_options: Mapping[str, Mapping[str, object]] | None = None,
        publisher_registry: PublisherRegistry | None = None,
    ) -> None:
        self._targets = tuple(dict.fromkeys(target.strip() for target in targets if target.strip()))
        self._publisher_options = dict(publisher_options or {})
        self._publisher_registry = publisher_registry or PublisherRegistry.get_instance()

    @property
    def enabled(self) -> bool:
        """Return whether any explicit target is configured."""
        return bool(self._targets)

    async def notify(
        self,
        regression: RegressionDetected,
        *,
        dataset_name: str,
        model: str,
        report_path: str,
    ) -> None:
        """Fan out a redacted regression alert without masking the gate failure."""
        if not self._targets:
            return
        payload = self._message(regression, dataset_name, model, report_path)
        for target in self._targets:
            try:
                publisher_class = self._publisher_registry.get(target)
                await publisher_class().publish(payload, self._publisher_options.get(target))
            except Exception as exc:  # Alert failures must never hide a regression gate.
                log.warning(
                    "regression_notification_failed",
                    target=target,
                    dimension=regression.dimension,
                    error_type=type(exc).__name__,
                )

    @staticmethod
    def _message(
        regression: RegressionDetected,
        dataset_name: str,
        model: str,
        report_path: str,
    ) -> str:
        """Render non-sensitive metadata for an external publisher."""
        dimensions = ", ".join(regression.violations)
        return "\n".join(
            (
                "Alert: eval_regression_detected",
                f"Dataset: {dataset_name}",
                f"Model: {model or 'unknown'}",
                f"Dimension: {regression.dimension}",
                f"All violations: {dimensions}",
                f"Baseline: {regression.baseline}",
                f"Current: {regression.current}",
                f"Threshold: {regression.threshold}",
                f"Report: {report_path}",
            )
        )


__all__ = ["RegressionNotifier"]
