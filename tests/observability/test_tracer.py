from multiscribe_agent.observability import tracer
from multiscribe_agent.observability.optional import ObservabilityCapabilities
from multiscribe_agent.observability.tracer import setup_tracer, trace_span


def test_setup_tracer_degrades_to_noop(monkeypatch) -> None:
    monkeypatch.setattr(
        tracer,
        "detect",
        lambda: ObservabilityCapabilities(tracer=False, meter=False, prometheus_endpoint=False),
    )
    monkeypatch.setattr(tracer, "_tracer", None)
    assert setup_tracer().start_as_current_span("x") is not None


def test_trace_span_context_degrades_to_noop(monkeypatch) -> None:
    monkeypatch.setattr(
        tracer,
        "detect",
        lambda: ObservabilityCapabilities(tracer=False, meter=False, prometheus_endpoint=False),
    )
    monkeypatch.setattr(tracer, "_tracer", None)
    with trace_span("test", {"key": "value"}) as span:
        span.set_attribute("ok", True)


def test_setup_tracer_is_cached(monkeypatch) -> None:
    monkeypatch.setattr(
        tracer,
        "detect",
        lambda: ObservabilityCapabilities(tracer=False, meter=False, prometheus_endpoint=False),
    )
    monkeypatch.setattr(tracer, "_tracer", None)
    first = setup_tracer()
    assert setup_tracer() is first
