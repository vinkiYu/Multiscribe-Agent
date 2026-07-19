"""Optional tracing and metrics primitives used across the service."""

from multiscribe_agent.observability.meter import MetricsRegistry, get_metrics_registry
from multiscribe_agent.observability.optional import ObservabilityCapabilities, detect
from multiscribe_agent.observability.tracer import setup_tracer, trace_span

__all__ = [
    "MetricsRegistry",
    "ObservabilityCapabilities",
    "detect",
    "get_metrics_registry",
    "setup_tracer",
    "trace_span",
]
