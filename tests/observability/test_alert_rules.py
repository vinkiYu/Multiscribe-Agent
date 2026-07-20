"""Tests for threshold, rolling-window, and ratio alert rules."""

from __future__ import annotations

import asyncio

import pytest

from multiscribe_agent.observability.alerts import AlertEngine, AlertRule, load_rules


@pytest.mark.asyncio
async def test_alert_rules_fire_threshold_window_and_ratio_callbacks() -> None:
    """All supported rule types invoke callbacks with their rule name."""
    fired: list[str] = []

    async def callback(name: str, payload: dict[str, object]) -> None:
        del payload
        fired.append(name)

    engine = AlertEngine(
        [
            AlertRule("threshold", "cpu", "threshold", 0.8),
            AlertRule("window", "latency", "window", 10.0),
            AlertRule("ratio", "errors", "ratio", 0.0),
        ]
    )
    engine.add_callback(callback)
    engine.record("cpu", 0.9)
    engine.record("latency", 11.0)
    engine.record("errors", 1.0)
    engine.record("errors", 0.0)
    await asyncio.sleep(0)

    assert {"threshold", "window", "ratio"}.issubset(fired)


def test_load_builtin_alert_rules() -> None:
    """The shipped rule file parses into all three evaluation modes."""
    from pathlib import Path

    rules = load_rules(Path("src/multiscribe_agent/observability/alert_rules.yaml"))
    assert {rule.type for rule in rules} == {"threshold", "window", "ratio"}
