from multiscribe_agent.observability import optional
from multiscribe_agent.observability.optional import ObservabilityCapabilities, detect


def test_detect_returns_capabilities() -> None:
    capabilities = detect()
    assert isinstance(capabilities.tracer, bool)
    assert isinstance(capabilities.meter, bool)
    assert isinstance(capabilities.prometheus_endpoint, bool)


def test_detect_handles_missing_parent_module(monkeypatch) -> None:
    monkeypatch.setattr(optional, "_has_module", lambda _name: False)
    capabilities = detect()
    assert capabilities == ObservabilityCapabilities(
        tracer=False, meter=False, prometheus_endpoint=False
    )


def test_detect_can_report_all_available(monkeypatch) -> None:
    monkeypatch.setattr(optional, "_has_module", lambda _name: True)
    capabilities = detect()
    assert capabilities.tracer
    assert capabilities.meter
    assert capabilities.prometheus_endpoint
