"""Tests for drift detection and workflow-event trace collection (P64.2 T12/T13)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from multiscribe_agent.agents.workflow.engine import WorkflowEngine
from multiscribe_agent.agents.workflow.events import WorkflowEvent
from multiscribe_agent.domain.models import WorkflowDefinition, WorkflowStep
from multiscribe_agent.eval.drift import DriftDetector, TrendPoint, load_snapshots
from multiscribe_agent.eval.trace_collector import TraceCollector


def _point(label: str, f1: float, tokens: int = 7000, p95: float = 23000.0) -> TrendPoint:
    return TrendPoint(
        label=label,
        avg_f1=f1,
        avg_precision=f1,
        avg_recall=f1,
        avg_tokens=tokens,
        p50_latency_ms=12000.0,
        p95_latency_ms=p95,
    )


def test_drift_falling_f1_alerts() -> None:
    detector = DriftDetector()
    alerts = detector.detect([_point("a", 0.79), _point("b", 0.77), _point("c", 0.74)])
    assert [alert.dimension for alert in alerts] == ["avg_f1", "avg_precision", "avg_recall"]
    assert alerts[0].round_labels == ("a", "b", "c")


def test_drift_rising_and_flat_stay_silent() -> None:
    detector = DriftDetector()
    assert detector.detect([_point("a", 0.74), _point("b", 0.77), _point("c", 0.79)]) == []
    assert detector.detect([_point("a", 0.78), _point("b", 0.78), _point("c", 0.78)]) == []


def test_drift_cost_dimension_alerts_on_increase() -> None:
    detector = DriftDetector()
    rising_cost = [
        _point("a", 0.78, tokens=7000, p95=23000.0),
        _point("b", 0.78, tokens=8000, p95=25000.0),
        _point("c", 0.78, tokens=9000, p95=27000.0),
    ]
    alerts = detector.detect(rising_cost)
    assert {alert.dimension for alert in alerts} == {"avg_tokens", "p95_latency_ms"}


def test_drift_skips_missing_cost_history() -> None:
    """Pre-P64.1 snapshots carry 0 tokens; those windows must not alert."""
    detector = DriftDetector()
    points = [
        _point("a", 0.78, tokens=0, p95=0.0),
        _point("b", 0.78, tokens=8000, p95=0.0),
        _point("c", 0.78, tokens=9000, p95=27000.0),
    ]
    alerts = detector.detect(points)
    assert "avg_tokens" not in {alert.dimension for alert in alerts}


def test_load_snapshots_orders_and_reads_live_last(tmp_path: Path) -> None:
    base = {"avg_f1": 0.77, "avg_precision": 0.77, "avg_recall": 0.84,
            "avg_tokens": 0, "p50_latency_ms": 0.0, "p95_latency_ms": 0.0}
    (tmp_path / "curation_recall_20260809-000000.json").write_text(
        json.dumps(base), encoding="utf-8"
    )
    (tmp_path / "curation_recall.json").write_text(
        json.dumps({**base, "avg_f1": 0.79}), encoding="utf-8"
    )
    points = load_snapshots(tmp_path)
    assert [p.label for p in points] == ["20260809-000000", "current"]
    assert points[-1].avg_f1 == 0.79


class _WorkflowStore:
    def __init__(self, workflow: WorkflowDefinition) -> None:
        self.workflow = workflow.model_dump(mode="json")

    async def get(self, table: str, entity_id: str) -> dict[str, object] | None:
        assert table == "workflows"
        return self.workflow if entity_id == "three-step" else None


class _Executor:
    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on

    async def execute(self, agent_id: str, user_input: str) -> str:
        if agent_id == self.fail_on:
            raise RuntimeError(f"{agent_id} failed")
        return f"{agent_id}:{user_input}"


def _three_step_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="three-step",
        name="three-step",
        description="P64.2 trace integration fixture",
        steps=[
            WorkflowStep(id="a", name="a", step_type="agent", agent_id="a", next_step_id="b"),
            WorkflowStep(id="b", name="b", step_type="agent", agent_id="b", next_step_id="c"),
            WorkflowStep(id="c", name="c", step_type="agent", agent_id="c"),
        ],
    )


@pytest.mark.asyncio
async def test_trace_consume_real_workflow_stream_distinguishes_three_and_two() -> None:
    """A real WorkflowEngine.stream feeds 3/3 success versus 2/3 failure."""
    workflow = _three_step_workflow()
    success = TraceCollector()
    success_engine = WorkflowEngine(_Executor(), _WorkflowStore(workflow))
    await success.consume(success_engine.stream("three-step", "start", run_id="success"))
    assert success.aggregate()[0] == 1.0

    failed = TraceCollector()
    failed_engine = WorkflowEngine(_Executor(fail_on="c"), _WorkflowStore(workflow))
    await failed.consume(failed_engine.stream("three-step", "start", run_id="failed"))
    assert abs(failed.aggregate()[0] - 2 / 3) < 1e-9


def _event(type_: str, trace_id: str, **data: object) -> WorkflowEvent:
    return WorkflowEvent(type=type_, data=dict(data), trace_id=trace_id)  # type: ignore[arg-type]


def test_workflow_events_three_of_three() -> None:
    collector = TraceCollector()
    for step in ("fetch", "curate", "digest"):
        collector.on_event(_event("step_start", "run-1", step_id=step))
    for step in ("fetch", "curate", "digest"):
        collector.on_event(_event("step_complete", "run-1", step_id=step))
    step_success, avg_steps, plan_match, retry_rate = collector.aggregate()
    assert step_success == 1.0
    assert avg_steps == 3.0
    assert plan_match == 1.0
    assert retry_rate == 0.0


def test_workflow_events_two_of_three_distinguishes() -> None:
    collector = TraceCollector()
    for step in ("fetch", "curate", "digest"):
        collector.on_event(_event("step_start", "run-1", step_id=step))
    collector.on_event(_event("step_complete", "run-1", step_id="fetch"))
    collector.on_event(_event("step_complete", "run-1", step_id="curate"))
    collector.on_event(_event("step_error", "run-1", step_id="digest"))
    collector.on_event(_event("loop_iteration", "run-1", retry=1))
    step_success, avg_steps, plan_match, retry_rate = collector.aggregate()
    assert abs(step_success - 2 / 3) < 1e-9
    assert avg_steps == 2.0
    assert plan_match == 1.0
    assert retry_rate == 1.0
