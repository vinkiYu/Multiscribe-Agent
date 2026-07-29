"""Integration-level tests for metric alert delivery wiring."""

from __future__ import annotations

import asyncio

import pytest

from multiscribe_agent.config import SystemSettings
from multiscribe_agent.observability.alerts import AlertEngine, AlertRule
from multiscribe_agent.observability.meter import MetricsRegistry
from multiscribe_agent.observability.optional import ObservabilityCapabilities
from multiscribe_agent.observability.publisher_alert_callback import PublisherAlertCallback


def _caps() -> ObservabilityCapabilities:
    return ObservabilityCapabilities(tracer=False, meter=False, prometheus_endpoint=False)


@pytest.mark.asyncio
async def test_publish_ratio_reaches_callback() -> None:
    fired: list[tuple[str, dict[str, object]]] = []

    async def callback(name: str, payload: dict[str, object]) -> None:
        fired.append((name, payload))

    engine = AlertEngine([AlertRule("publish", "publish_failure", "ratio", 0.0)])
    engine.add_callback(callback)
    registry = MetricsRegistry.create(_caps())
    registry.alert_engine = engine
    registry.record_publish(False, 0.1)
    registry.record_publish(True, 0.1)
    await asyncio.sleep(0)
    assert fired
    assert fired[0][0] == "publish"
    assert fired[0][1]["metric"] == "publish_failure"


@pytest.mark.asyncio
async def test_publisher_alert_callback_isolates_target_failures() -> None:
    delivered: list[str] = []

    class GoodPublisher:
        async def publish(self, content: object, options: object = None) -> dict[str, object]:
            del options
            delivered.append(str(content))
            return {"ok": True}

    class BadPublisher:
        async def publish(self, content: object, options: object = None) -> dict[str, object]:
            del content, options
            raise RuntimeError("unavailable")

    class Registry:
        def get(self, target: str) -> type[object]:
            return {"bad": BadPublisher, "good": GoodPublisher}[target]

    callback = PublisherAlertCallback(
        ["bad", "good"],
        {},
        publisher_registry=Registry(),  # type: ignore[arg-type]
    )
    await callback(
        "publish_failure",
        {
            "metric": "publish_failure",
            "threshold": 0,
            "description": "failure ratio",
            "timestamp": 1,
        },
    )
    assert len(delivered) == 1
    assert "publish_failure" in delivered[0]


def test_alert_targets_support_both_environment_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALERT_TARGETS", "feishu_bot,wecom_bot")
    settings = SystemSettings(_env_file=None)
    assert settings.alert_targets == "feishu_bot,wecom_bot"
    monkeypatch.delenv("ALERT_TARGETS")
    monkeypatch.setenv("MULTISCRIBE_ALERT_TARGETS", "feishu_bot")
    assert SystemSettings(_env_file=None).alert_targets == "feishu_bot"
