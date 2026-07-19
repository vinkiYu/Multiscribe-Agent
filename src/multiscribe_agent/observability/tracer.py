"""OTel tracer setup with a graceful no-op fallback."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from importlib import import_module
from typing import Protocol, cast

from multiscribe_agent.observability.optional import detect


class SpanLike(Protocol):
    """Small span surface used by instrumentation callers."""

    def set_attribute(self, *args: object, **kwargs: object) -> None: ...

    def record_exception(self, *args: object, **kwargs: object) -> None: ...


class TracerLike(Protocol):
    """Small tracer surface used to open context-managed spans."""

    def start_as_current_span(
        self, *args: object, **kwargs: object
    ) -> AbstractContextManager[SpanLike]: ...


_tracer: TracerLike | None = None


def setup_tracer() -> TracerLike:
    """Initialize the process tracer provider or return a no-op tracer."""
    global _tracer
    if _tracer is not None:
        return _tracer
    capabilities = detect()
    if not capabilities.tracer:
        _tracer = _NoopTracer()
        return _tracer
    try:
        trace = import_module("opentelemetry.trace")
        resources = import_module("opentelemetry.sdk.resources")
        sdk_trace = import_module("opentelemetry.sdk.trace")
        sdk_export = import_module("opentelemetry.sdk.trace.export")
    except ImportError:
        _tracer = _NoopTracer()
        return _tracer

    provider = sdk_trace.TracerProvider(
        resource=resources.Resource.create({"service.name": "multiscribe-agent"})
    )
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        try:
            exporter = import_module("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")

            provider.add_span_processor(
                sdk_export.BatchSpanProcessor(exporter.OTLPSpanExporter(endpoint=endpoint))
            )
        except ImportError:
            provider.add_span_processor(
                sdk_export.BatchSpanProcessor(sdk_export.ConsoleSpanExporter())
            )
    else:
        provider.add_span_processor(sdk_export.BatchSpanProcessor(sdk_export.ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _tracer = cast(TracerLike, trace.get_tracer("multiscribe-agent"))
    return _tracer


@contextmanager
def trace_span(name: str, attributes: dict[str, object] | None = None) -> Iterator[SpanLike]:
    """Start one current span, falling back to a no-op context when unavailable."""
    tracer = setup_tracer()
    with tracer.start_as_current_span(name, attributes=attributes or {}) as span:
        yield span


class _NoopTracer:
    def start_as_current_span(self, *_args: object, **_kwargs: object) -> _NoopSpan:
        return _NoopSpan()


class _NoopSpan:
    def set_attribute(self, *_args: object, **_kwargs: object) -> None:
        return None

    def record_exception(self, *_args: object, **_kwargs: object) -> None:
        return None

    def __enter__(self) -> _NoopSpan:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        return None
