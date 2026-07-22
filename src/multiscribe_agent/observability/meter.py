"""Centralized metrics with OTel-compatible recording and text fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from typing import Any

from multiscribe_agent.observability.optional import ObservabilityCapabilities, detect


@dataclass(slots=True)
class MetricsRegistry:
    """Record counters and histograms regardless of optional backend availability."""

    capabilities: ObservabilityCapabilities
    _counters: dict[str, Any] = field(default_factory=dict)
    _histograms: dict[str, Any] = field(default_factory=dict)
    _counts: dict[str, int] = field(default_factory=dict)
    _histogram_values: dict[str, list[float]] = field(default_factory=dict)

    @classmethod
    def create(cls, capabilities: ObservabilityCapabilities | None = None) -> MetricsRegistry:
        """Create a registry and opportunistically bind OTel instruments."""
        resolved = capabilities or detect()
        registry = cls(resolved)
        for name in (
            "publish_success",
            "publish_failure",
            "llm_calls",
            "llm_tokens",
            "tool_calls",
            "context_compactions",
            "context_degradations",
            "context_budget_exhaustions",
        ):
            registry._counts[name] = 0
        for name in ("llm_latency", "publish_latency"):
            registry._histogram_values[name] = []
        if resolved.meter:
            try:
                metrics = import_module("opentelemetry.metrics")

                meter = metrics.get_meter("multiscribe-agent")
                registry._counters = {
                    name: meter.create_counter(f"multiscribe_{name}_total")
                    for name in (
                        "publish_success",
                        "publish_failure",
                        "llm_calls",
                        "llm_tokens",
                        "tool_calls",
                        "context_compactions",
                        "context_degradations",
                        "context_budget_exhaustions",
                    )
                }
                registry._histograms = {
                    name: meter.create_histogram(f"multiscribe_{name}_seconds")
                    for name in ("llm_latency", "publish_latency")
                }
            except (ImportError, RuntimeError):
                registry._counters = {}
                registry._histograms = {}
        return registry

    def record_publish(self, success: bool, duration_seconds: float) -> None:
        """Record one publishing outcome and latency."""
        name = "publish_success" if success else "publish_failure"
        self._record_counter(name)
        self._record_histogram("publish_latency", duration_seconds)

    def record_llm_call(self, tokens: int, duration_seconds: float) -> None:
        """Record one LLM call plus its token count."""
        self._record_counter("llm_calls")
        self._record_counter("llm_tokens", amount=max(tokens, 0))
        self._record_histogram("llm_latency", duration_seconds)

    def record_tool_call(self, tool_name: str) -> None:
        """Record one tool invocation; the name is reserved for future labels."""
        del tool_name
        self._record_counter("tool_calls")

    def record_context_event(self, event: str) -> None:
        """Record context lifecycle outcomes without retaining prompt content."""
        names = {
            "compacted": "context_compactions",
            "degraded": "context_degradations",
            "budget_exhausted": "context_budget_exhaustions",
        }
        name = names.get(event)
        if name is not None:
            self._record_counter(name)

    def render_prometheus(self) -> str:
        """Render a dependency-free Prometheus text exposition."""
        lines: list[str] = []
        for name, value in self._counts.items():
            metric = f"multiscribe_{name}_total"
            lines.extend([f"# TYPE {metric} counter", f"{metric} {value}"])
        for name, values in self._histogram_values.items():
            metric = f"multiscribe_{name}_seconds"
            lines.extend(
                [
                    f"# TYPE {metric} histogram",
                    f"{metric}_count {len(values)}",
                    f"{metric}_sum {sum(values):.6f}",
                ]
            )
        return "\n".join(lines) + "\n"

    def _record_counter(self, name: str, amount: int = 1) -> None:
        self._counts[name] = self._counts.get(name, 0) + amount
        instrument = self._counters.get(name)
        if instrument is not None:
            instrument.add(amount)

    def _record_histogram(self, name: str, value: float) -> None:
        self._histogram_values.setdefault(name, []).append(value)
        instrument = self._histograms.get(name)
        if instrument is not None:
            instrument.record(value)


_default_registry = MetricsRegistry.create()


def get_metrics_registry() -> MetricsRegistry:
    """Return the process-wide fallback registry used by instrumentation."""
    return _default_registry


def set_metrics_registry(registry: MetricsRegistry) -> None:
    """Replace the process-wide registry during application bootstrap."""
    global _default_registry
    _default_registry = registry
