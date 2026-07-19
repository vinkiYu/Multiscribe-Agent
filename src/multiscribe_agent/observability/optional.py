"""Detect optional observability dependencies and expose degradation flags."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec


@dataclass(frozen=True, slots=True)
class ObservabilityCapabilities:
    """Availability of each optional observability backend."""

    tracer: bool
    meter: bool
    prometheus_endpoint: bool


def detect() -> ObservabilityCapabilities:
    """Probe runtime modules without importing unavailable optional packages."""
    otel_api = _has_module("opentelemetry")
    return ObservabilityCapabilities(
        tracer=otel_api and _has_module("opentelemetry.trace"),
        meter=otel_api and _has_module("opentelemetry.metrics"),
        prometheus_endpoint=_has_module("prometheus_client"),
    )


def _has_module(name: str) -> bool:
    """Return whether a possibly nested optional module can be found."""
    try:
        return find_spec(name) is not None
    except ModuleNotFoundError:
        return False
