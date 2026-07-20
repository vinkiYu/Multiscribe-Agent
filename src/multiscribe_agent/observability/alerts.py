"""Configurable alert rule engine evaluating metrics against thresholds."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]

type AlertCallback = Callable[[str, dict[str, object]], Awaitable[None]]
type RuleType = Literal["threshold", "window", "ratio"]


@dataclass(frozen=True, slots=True)
class AlertRule:
    """One metric rule evaluated by :class:`AlertEngine`."""

    name: str
    metric: str
    type: RuleType
    threshold: float
    window_seconds: int = 60
    description: str = ""


@dataclass
class AlertEngine:
    """Evaluate threshold, rolling-window, and breach-ratio rules."""

    rules: list[AlertRule]
    _values: dict[str, deque[tuple[float, float]]] = field(default_factory=dict)
    _callbacks: list[AlertCallback] = field(default_factory=list)
    _tasks: set[asyncio.Task[None]] = field(default_factory=set, init=False, repr=False)

    def add_callback(self, callback: AlertCallback) -> None:
        """Register a callback invoked when a rule is breached."""
        self._callbacks.append(callback)

    def record(self, metric: str, value: float) -> None:
        """Push one metric sample and schedule callbacks for breached rules."""
        now = time.monotonic()
        samples = self._values.setdefault(metric, deque(maxlen=10_000))
        samples.append((now, value))
        for rule in self.rules:
            if rule.metric == metric and self._breached(rule, now):
                self._schedule_fire(rule, metric)

    def is_breached(self, rule: AlertRule) -> bool:
        """Return the current breach state for a rule."""
        return self._breached(rule, time.monotonic())

    def _breached(self, rule: AlertRule, now: float) -> bool:
        samples = [
            value
            for timestamp, value in self._values.get(rule.metric, ())
            if now - timestamp <= rule.window_seconds
        ]
        if not samples:
            return False
        if rule.type == "threshold":
            return samples[-1] > rule.threshold
        if rule.type == "window":
            return sum(samples) / len(samples) > rule.threshold
        if rule.type == "ratio":
            return sum(value > rule.threshold for value in samples) / len(samples) > 0.5
        return False

    def _schedule_fire(self, rule: AlertRule, metric: str) -> None:
        """Schedule async callbacks only when an event loop is active."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self._fire(rule, metric))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _fire(self, rule: AlertRule, metric: str) -> None:
        payload: dict[str, object] = {
            "rule": rule.name,
            "metric": metric,
            "threshold": rule.threshold,
            "description": rule.description,
            "timestamp": int(time.time()),
        }
        for callback in tuple(self._callbacks):
            try:
                await callback(rule.name, payload)
            except (RuntimeError, OSError, ValueError, TypeError):
                continue


def load_rules(path: Path) -> list[AlertRule]:
    """Load validated alert rules from a YAML file."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("alert rules document must be an object")
    raw_rules = raw.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError("alert rules must be a list")
    rules: list[AlertRule] = []
    for item in raw_rules:
        if not isinstance(item, dict):
            raise ValueError("each alert rule must be an object")
        rule_type = str(item.get("type", "threshold"))
        if rule_type not in {"threshold", "window", "ratio"}:
            raise ValueError(f"unsupported alert rule type: {rule_type}")
        rules.append(
            AlertRule(
                name=str(item["name"]),
                metric=str(item["metric"]),
                type=rule_type,  # type: ignore[arg-type]
                threshold=float(item["threshold"]),
                window_seconds=int(item.get("window_seconds", 60)),
                description=str(item.get("description", "")),
            )
        )
    return rules
