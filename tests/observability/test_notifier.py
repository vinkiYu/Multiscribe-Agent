"""Tests for explicitly enabled evaluation regression notifications."""

from __future__ import annotations

from typing import cast

import pytest

from multiscribe_agent.eval.benchmark import RegressionDetected
from multiscribe_agent.observability.notifier import RegressionNotifier
from multiscribe_agent.plugins.registry import PublisherRegistry


class RecordingPublisher:
    """Record publish calls into a module-level list for assertions."""

    def __init__(self) -> None:
        self.messages = _messages

    async def publish(self, content: str, options: dict[str, object] | None = None) -> str:
        _messages.append((content, options))
        return "published"


class FailingPublisher:
    async def publish(self, content: str, options: dict[str, object] | None = None) -> str:
        del content, options
        raise RuntimeError("delivery failed")


_messages: list[tuple[str, dict[str, object] | None]] = []


class FakeRegistry:
    def get(self, target: str) -> type[RecordingPublisher]:
        if target != "good":
            raise KeyError(target)
        return RecordingPublisher


class MixedRegistry:
    def get(self, target: str) -> type[RecordingPublisher] | type[FailingPublisher]:
        return FailingPublisher if target == "bad" else RecordingPublisher


@pytest.fixture(autouse=True)
def reset_messages() -> None:
    _messages.clear()


@pytest.mark.asyncio
async def test_default_notifier_is_disabled_and_makes_no_publish_call() -> None:
    notifier = RegressionNotifier(publisher_registry=cast("PublisherRegistry", FakeRegistry()))
    regression = RegressionDetected(0.9, 0.8, 0.05, dimension="precision")

    await notifier.notify(regression, dataset_name="fixture", model="gpt-test", report_path="r.md")

    assert not notifier.enabled
    assert _messages == []


@pytest.mark.asyncio
async def test_enabled_notifier_sends_redacted_structured_message() -> None:
    notifier = RegressionNotifier(
        targets=["good"],
        publisher_options={"good": {"webhook": "https://secret.example"}},
        publisher_registry=cast("PublisherRegistry", FakeRegistry()),
    )
    regression = RegressionDetected(
        0.9,
        0.8,
        0.05,
        dimension="precision",
        violations=("precision", "phase_f1"),
    )

    await notifier.notify(regression, dataset_name="fixture", model="gpt-test", report_path="r.md")

    assert notifier.enabled
    message, options = _messages[0]
    assert "Alert: eval_regression_detected" in message
    assert "Dimension: precision" in message
    assert "All violations: precision, phase_f1" in message
    assert "https://secret.example" not in message
    assert options == {"webhook": "https://secret.example"}


@pytest.mark.asyncio
async def test_delivery_failure_does_not_raise_or_block_other_target() -> None:
    notifier = RegressionNotifier(
        targets=["bad", "good"],
        publisher_registry=cast("PublisherRegistry", MixedRegistry()),
    )
    regression = RegressionDetected(0.9, 0.8, 0.05, dimension="precision")

    await notifier.notify(regression, dataset_name="fixture", model="gpt-test", report_path="r.md")

    assert len(_messages) == 1
