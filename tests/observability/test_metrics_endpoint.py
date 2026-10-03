from fastapi.testclient import TestClient

from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings
from multiscribe_agent.observability.meter import MetricsRegistry, set_metrics_registry
from multiscribe_agent.observability.optional import ObservabilityCapabilities
from tests.db import get_test_database_url


def _caps() -> ObservabilityCapabilities:
    return ObservabilityCapabilities(tracer=False, meter=False, prometheus_endpoint=False)


def test_metrics_endpoint_returns_text_exposition(tmp_path) -> None:
    registry = MetricsRegistry.create(_caps())
    registry.record_publish(True, 0.1)
    set_metrics_registry(registry)
    settings = SystemSettings(_env_file=None, database_url=get_test_database_url())
    context = ServiceContext(settings)
    with TestClient(create_app(settings, context)) as client:
        response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "multiscribe_publish_success_total" in response.text


def test_healthz_endpoint_returns_ok(tmp_path) -> None:
    settings = SystemSettings(_env_file=None, database_url=get_test_database_url())
    context = ServiceContext(settings)
    with TestClient(create_app(settings, context)) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_access_log_adds_trace_id_header(tmp_path) -> None:
    settings = SystemSettings(_env_file=None, database_url=get_test_database_url())
    context = ServiceContext(settings)
    with TestClient(create_app(settings, context)) as client:
        response = client.get("/healthz")
    assert len(response.headers["X-Trace-Id"]) == 32
