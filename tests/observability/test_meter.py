from multiscribe_agent.observability.meter import (
    MetricsRegistry,
    get_metrics_registry,
    set_metrics_registry,
)
from multiscribe_agent.observability.optional import ObservabilityCapabilities


def _caps() -> ObservabilityCapabilities:
    return ObservabilityCapabilities(tracer=False, meter=False, prometheus_endpoint=False)


def test_metrics_registry_records_publish_success() -> None:
    registry = MetricsRegistry.create(_caps())
    registry.record_publish(True, 0.25)
    text = registry.render_prometheus()
    assert "multiscribe_publish_success_total 1" in text
    assert "multiscribe_publish_latency_seconds_count 1" in text


def test_metrics_registry_records_publish_failure() -> None:
    registry = MetricsRegistry.create(_caps())
    registry.record_publish(False, 0.5)
    text = registry.render_prometheus()
    assert "multiscribe_publish_failure_total 1" in text
    assert "multiscribe_publish_latency_seconds_sum 0.500000" in text


def test_metrics_registry_records_llm_tokens_and_latency() -> None:
    registry = MetricsRegistry.create(_caps())
    registry.record_llm_call(42, 1.25)
    text = registry.render_prometheus()
    assert "multiscribe_llm_calls_total 1" in text
    assert "multiscribe_llm_tokens_total 42" in text
    assert "multiscribe_llm_latency_seconds_count 1" in text


def test_metrics_registry_records_tool_calls() -> None:
    registry = MetricsRegistry.create(_caps())
    registry.record_tool_call("kb_search")
    assert "multiscribe_tool_calls_total 1" in registry.render_prometheus()


def test_process_metrics_registry_can_be_replaced() -> None:
    registry = MetricsRegistry.create(_caps())
    set_metrics_registry(registry)
    assert get_metrics_registry() is registry


def test_provider_context_retry_metrics_are_exposed() -> None:
    registry = MetricsRegistry.create(_caps())
    registry.record_provider_context_event("rejected")
    registry.record_provider_context_event("retry")
    registry.record_provider_context_event("retry_success")

    text = registry.render_prometheus()
    assert "multiscribe_provider_context_rejections_total 1" in text
    assert "multiscribe_provider_context_retries_total 1" in text
    assert "multiscribe_provider_context_retry_success_total 1" in text
