"""Tests for parallel benchmark correctness and baseline archiving (P64.2 T9/T12)."""

from __future__ import annotations

import gzip
import json
import math
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import cast

import pytest

from multiscribe_agent.agents.workflow.events import WorkflowEvent
from multiscribe_agent.domain.models import AIMessage, AIResponse, TokenUsage
from multiscribe_agent.eval.benchmark import RegressionDetected
from multiscribe_agent.eval.collector.trace_sink import TraceSink
from multiscribe_agent.eval.curation_benchmark import (
    CurationBenchmarkSummary,
    _check_and_write_baseline,
    run_curation_benchmark,
)
from multiscribe_agent.eval.curation_dataset import (
    CurationCandidate,
    CurationDataset,
    CurationSample,
)
from multiscribe_agent.eval.ledger import load_ledger
from multiscribe_agent.eval.metrics_schema import MetricThresholds
from multiscribe_agent.llm.provider import AIProvider
from multiscribe_agent.observability.meter import MetricsRegistry, set_metrics_registry
from multiscribe_agent.observability.optional import detect


class SlowFakeProvider:
    """Yield deterministic selections with a small await-able delay."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, messages: list[AIMessage], **_: object) -> AIResponse:
        import asyncio

        self.calls += 1
        await asyncio.sleep(0.01)
        prompt = str(messages[0].content)
        import re

        ids = re.findall(r'"id":\s*"(cr-\d+-a1)"', prompt)
        return AIResponse(
            content=json.dumps([{"id": item} for item in sorted(set(ids))]),
            usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        )


def _dataset(count: int = 6) -> CurationDataset:
    samples = [
        CurationSample(
            id=f"cr-{index:03d}",
            candidates=[
                CurationCandidate(
                    id=f"cr-{index:03d}-a1",
                    title=f"Agent release {index}",
                    description="A useful Agent engineering release.",
                    url=f"https://example.test/{index}",
                    source="rss",
                ),
                CurationCandidate(
                    id=f"cr-{index:03d}-a2",
                    title=f"Weather {index}",
                    description="A general weather report.",
                    url=f"https://example.test/{index}-w",
                    source="rss",
                ),
            ],
            expected_selected_ids=[f"cr-{index:03d}-a1"],
            expected_rejected_ids=[f"cr-{index:03d}-a2"],
        )
        for index in range(1, count + 1)
    ]
    return CurationDataset(name="parallel", description="fixture", samples=samples)


@pytest.fixture
def isolated_meter() -> Iterator[MetricsRegistry]:
    registry = MetricsRegistry(capabilities=detect())
    set_metrics_registry(registry)
    yield registry
    set_metrics_registry(MetricsRegistry(capabilities=detect()))


@pytest.mark.asyncio
async def test_parallel_run_keeps_every_sample_and_meter_totals(
    tmp_path: Path, isolated_meter: MetricsRegistry
) -> None:
    """gather(concurrency=4) loses no samples and meter totals stay exact."""
    provider = SlowFakeProvider()
    dataset = _dataset(6)

    summary = await run_curation_benchmark(
        cast("AIProvider", provider), dataset, tmp_path / "reports", concurrency=4
    )

    assert summary.total == 6
    assert summary.passed == 6
    assert summary.avg_f1 == 1.0
    assert summary.avg_tokens == 150
    assert summary.step_success_rate == 1.0
    assert summary.p50_latency_ms > 0.0
    assert provider.calls == 6
    # meter aggregated every call exactly once regardless of interleaving
    assert len(isolated_meter.llm_latency_seconds()) == 6

    report = next((tmp_path / "reports").glob("*.md")).read_text(encoding="utf-8")
    assert "| 选择 |" in report
    assert "sel=cr-001-a1;exp=cr-001-a1" in report


async def _three_step_events() -> AsyncIterator[WorkflowEvent]:
    for step in ("fetch", "curate", "digest"):
        yield WorkflowEvent("step_start", {"step_id": step}, "workflow-run")
        yield WorkflowEvent("step_complete", {"step_id": step}, "workflow-run")


@pytest.mark.asyncio
async def test_benchmark_uses_supplied_workflow_events_for_process_metrics(tmp_path: Path) -> None:
    """Real workflow events override the single-step curator fallback metrics."""
    summary = await run_curation_benchmark(
        cast("AIProvider", SlowFakeProvider()),
        _dataset(2),
        tmp_path / "reports",
        workflow_events=_three_step_events(),
        concurrency=2,
    )
    assert summary.step_success_rate == 1.0
    assert summary.avg_steps_per_sample == 3.0
    assert summary.plan_match_rate == 1.0


@pytest.mark.asyncio
async def test_concurrency_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="concurrency"):
        await run_curation_benchmark(
            cast("AIProvider", SlowFakeProvider()),
            _dataset(1),
            tmp_path / "reports",
            concurrency=0
        )


@pytest.mark.asyncio
async def test_benchmark_persists_trace_sink(tmp_path: Path) -> None:
    """Each benchmark can persist its per-sample traces as one gzip JSONL file."""
    sink = TraceSink(tmp_path / "traces")
    await run_curation_benchmark(
        cast("AIProvider", SlowFakeProvider()),
        _dataset(3),
        tmp_path / "reports",
        trace_sink=sink,
        concurrency=3,
    )
    archives = list((tmp_path / "traces").glob("benchmark_*.jsonl.gz"))
    assert len(archives) == 1
    with gzip.open(archives[0], "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    assert [row["sample_id"] for row in rows] == ["cr-001", "cr-002", "cr-003"]


def test_relative_token_and_latency_gates_trigger(tmp_path: Path) -> None:
    """P64.2 ratio caps reject 20%+ token and p95 increases independently."""
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "avg_f1": 0.8,
                "avg_precision": 0.8,
                "avg_recall": 0.8,
                "step_success_rate": 1.0,
                "avg_tokens": 100,
                "p95_latency_ms": 100.0,
            }
        ),
        encoding="utf-8",
    )
    thresholds = MetricThresholds(
        max_tokens_per_sample=None,
        max_p95_latency_ms=None,
        token_increase_ratio=0.20,
        latency_p95_increase_ratio=0.20,
    )

    token_regressed = _summary_with_costs(tokens=121, p95_latency_ms=100.0)
    with pytest.raises(RegressionDetected):
        _check_and_write_baseline(token_regressed, baseline, 0.05, thresholds)

    latency_regressed = _summary_with_costs(tokens=100, p95_latency_ms=121.0)
    with pytest.raises(RegressionDetected):
        _check_and_write_baseline(latency_regressed, baseline, 0.05, thresholds)


def test_rejected_run_writes_all_dimensions_without_replacing_baseline(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    original = (
        '{"avg_f1": 0.8, "avg_precision": 0.9, "avg_recall": 0.8, '
        '"step_success_rate": 1.0, "avg_tokens": 100, "p95_latency_ms": 100.0}'
    )
    baseline.write_text(original, encoding="utf-8")
    summary = CurationBenchmarkSummary(
        dataset_name="fixture",
        total=1,
        passed=1,
        failed=0,
        avg_precision=0.8,
        avg_recall=0.8,
        avg_f1=0.7,
        overall=0.7,
        step_success_rate=0.8,
        avg_tokens=130,
        p95_latency_ms=130.0,
        wall_clock_seconds=12.0,
        report_path="report.md",
    )
    ledger = tmp_path / "rejected.jsonl"

    with pytest.raises(RegressionDetected) as raised:
        _check_and_write_baseline(
            summary,
            baseline,
            0.05,
            MetricThresholds(max_tokens_per_sample=None, max_p95_latency_ms=None),
            ledger_path=ledger,
            concurrency=4,
            model="gpt-test",
            phase_min_f1=0.8,
        )

    assert set(raised.value.violations) >= {
        "f1",
        "precision",
        "step_success_rate",
        "avg_tokens_ratio",
        "p95_latency_ratio",
        "phase_f1",
    }
    assert baseline.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("baseline_*.json")) == []
    record = load_ledger(ledger)[0]
    assert record.rejected_dimensions == list(raised.value.violations)
    assert record.report_path == "report.md"
    assert record.wall_clock_seconds == 12.0


def _summary_with_costs(tokens: int, p95_latency_ms: float) -> CurationBenchmarkSummary:
    return CurationBenchmarkSummary(
        dataset_name="fixture",
        total=1,
        passed=1,
        failed=0,
        avg_precision=0.8,
        avg_recall=0.8,
        avg_f1=0.8,
        overall=0.8,
        step_success_rate=1.0,
        avg_tokens=tokens,
        p95_latency_ms=p95_latency_ms,
    )


@pytest.mark.asyncio
async def test_baseline_overwrite_archives_previous(tmp_path: Path) -> None:
    """The second run snapshots the first baseline before overwriting it."""
    baseline = tmp_path / "b.json"
    await run_curation_benchmark(
        cast("AIProvider", SlowFakeProvider()),
        _dataset(2),
        tmp_path / "reports",
        baseline_path=baseline,
    )
    first = json.loads(baseline.read_text(encoding="utf-8"))

    await run_curation_benchmark(
        cast("AIProvider", SlowFakeProvider()),
        _dataset(2),
        tmp_path / "reports",
        baseline_path=baseline,
        thresholds=MetricThresholds(latency_p95_increase_ratio=math.inf),
    )
    second = json.loads(baseline.read_text(encoding="utf-8"))

    archives = list(tmp_path.glob("b_*.json"))
    assert len(archives) == 1
    assert json.loads(archives[0].read_text(encoding="utf-8")) == first
    assert second["total"] == 2
