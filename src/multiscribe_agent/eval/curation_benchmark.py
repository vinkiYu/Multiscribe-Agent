"""Run real-curator curation benchmarks with deterministic ground-truth scoring.
P64.1: integrate per-layer metrics (process + efficiency + safety) on top of
the existing result-layer summary, and emit a multi-dimensional regression gate.
"""

from __future__ import annotations

import asyncio
import json
import math
import shutil
import time
from collections.abc import AsyncIterable, Mapping
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import structlog

from multiscribe_agent.agents.pipelines.daily_digest import (
    CURATE_SUMMARY_CHAR_LIMIT,
    fallback_summary,
)
from multiscribe_agent.agents.pipelines.prompts import CURATE_PROMPT
from multiscribe_agent.agents.workflow.events import WorkflowEvent
from multiscribe_agent.core.errors import ProviderError
from multiscribe_agent.domain.models import AIMessage, AIResponse
from multiscribe_agent.eval.benchmark import RegressionDetected
from multiscribe_agent.eval.collector.trace_sink import TraceSink
from multiscribe_agent.eval.curation_dataset import CurationDataset, CurationSample
from multiscribe_agent.eval.curation_scorer import CurationScore, score_curation
from multiscribe_agent.eval.ledger import RejectedRun, append_rejected
from multiscribe_agent.eval.metrics_schema import EvalMetrics, MetricThresholds
from multiscribe_agent.eval.safety_gate import SafetyGate, SafetyReport
from multiscribe_agent.eval.trace_collector import TraceCollector
from multiscribe_agent.llm.provider import AIProvider
from multiscribe_agent.observability.meter import MetricsRegistry, get_metrics_registry
from multiscribe_agent.observability.notifier import RegressionNotifier

CURATION_SYSTEM_INSTRUCTION = "You are a careful Chinese AI news curation assistant."

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CurationBenchmarkResult:
    """Ground-truth score for one benchmark sample."""

    sample_id: str
    precision: float
    recall: float
    f1: float
    passed: bool


@dataclass(frozen=True, slots=True)
class CurationBenchmarkSummary:
    """Aggregate curation score written to the optional regression baseline."""

    dataset_name: str
    total: int
    passed: int
    failed: int
    avg_precision: float
    avg_recall: float
    avg_f1: float
    overall: float
    report_path: str = ""

    # P64.1 additions: process / efficiency / safety aggregates
    step_success_rate: float = 1.0
    avg_steps_per_sample: float = 0.0
    plan_match_rate: float = 1.0
    retry_rate: float = 0.0
    avg_tokens: int = 0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    avg_tool_calls: int = 0
    wall_clock_seconds: float = 0.0
    injection_blocked: int = 0
    pii_violations: int = 0
    permission_violations: int = 0


async def run_curation(provider: AIProvider, sample: CurationSample, target_count: int) -> set[str]:
    """Ask the configured curator to select candidate IDs for one sample."""
    selected, _ = await run_curation_with_response(provider, sample, target_count)
    return selected


async def run_curation_with_response(
    provider: AIProvider, sample: CurationSample, target_count: int
) -> tuple[set[str], AIResponse]:
    """Run one curation call and return the selected IDs plus the raw response.

    The raw response carries ``usage`` (token accounting) and the output text
    consumed by the SafetyGate output check.
    """
    if target_count < 1:
        raise ValueError("target_count must be positive")
    items = [_project_candidate(candidate) for candidate in sample.candidates]
    prompt = CURATE_PROMPT.format(
        items=json.dumps(items, ensure_ascii=False, sort_keys=True),
        feedback="无",
        target_count=target_count,
        preferred_tags="（无）",
        blocked_topics="（无）",
        kb_snippets="（无）",
    )
    response = await provider.generate(
        [AIMessage(role="user", content=prompt)],
        system_instruction=CURATION_SYSTEM_INSTRUCTION,
    )
    return _selected_ids(response.content), response


async def run_curation_benchmark(
    provider: AIProvider,
    dataset: CurationDataset,
    reports_dir: Path,
    baseline_path: Path | None = None,
    threshold: float = 0.10,
    target_count: int = 12,
    thresholds: MetricThresholds | None = None,
    safety_gate: SafetyGate | None = None,
    trace_collector: TraceCollector | None = None,
    workflow_events: AsyncIterable[WorkflowEvent] | None = None,
    trace_sink: TraceSink | None = None,
    ledger_path: Path | None = None,
    model: str = "",
    phase_min_f1: float | None = None,
    notifier: RegressionNotifier | None = None,
    # N=8 was fastest in the 20-sample T9 sweep. Full 100-sample quality
    # drift later appeared under both N=8 and N=4, so N=4 is a conservative
    # throughput default, not a proven remedy for provider-side drift.
    concurrency: int = 4,
) -> CurationBenchmarkSummary:
    """Run all samples (bounded-parallel), write a Markdown report, and gate regressions.

    Aggregation relies on per-sample counters returned by ``_run_sample`` only;
    shared/global timing (e.g. slicing the meter histogram by offset) is
    intentionally avoided because it is not concurrency-safe.
    """
    if not threshold >= 0.0:
        raise ValueError("threshold must not be negative")
    if concurrency < 1:
        raise ValueError("concurrency must be positive")
    selected_thresholds = thresholds or MetricThresholds()
    benchmark_started = time.perf_counter()
    meter = get_metrics_registry()
    fallback_collector = trace_collector or TraceCollector()
    event_collector = TraceCollector() if workflow_events is not None else None
    collector = event_collector or fallback_collector
    safety = safety_gate or SafetyGate()
    event_task = (
        asyncio.create_task(event_collector.consume(workflow_events))
        if event_collector is not None and workflow_events is not None
        else None
    )

    semaphore = asyncio.Semaphore(concurrency)

    async def _guarded(sample: CurationSample) -> _SampleRun:
        async with semaphore:
            return await _run_sample(
                provider, sample, target_count, safety, fallback_collector, meter
            )

    # asyncio.gather preserves dataset order, so the report stays deterministic.
    try:
        runs = await asyncio.gather(*(_guarded(sample) for sample in dataset.samples))
        if event_task is not None:
            await event_task
    finally:
        if event_task is not None and not event_task.done():
            event_task.cancel()
            with suppress(asyncio.CancelledError):
                await event_task
    if trace_sink is not None:
        trace_sink.write(collector.all_traces())
    wall_clock_seconds = time.perf_counter() - benchmark_started

    results = [(run.result, run.score) for run in runs]
    injection_count = sum(run.injection_count for run in runs)
    pii_count = sum(run.pii_count for run in runs)
    total_tokens = sum(run.tokens for run in runs)
    durations = [run.duration_seconds for run in runs]
    safety_flags = {run.result.sample_id: run.flagged_ids for run in runs if run.flagged_ids}

    summary = _summarize(
        dataset.name,
        results,
        collector,
        injection_count=injection_count,
        pii_count=pii_count,
        total_tokens=total_tokens,
        latencies=durations,
        wall_clock_seconds=wall_clock_seconds,
    )
    report_path = _write_report(dataset, results, summary, reports_dir, safety_flags)
    summary = CurationBenchmarkSummary(**{**asdict(summary), "report_path": str(report_path)})
    if baseline_path is not None:
        try:
            _check_and_write_baseline(
                summary,
                baseline_path,
                threshold,
                selected_thresholds,
                ledger_path=ledger_path,
                concurrency=concurrency,
                model=model,
                phase_min_f1=phase_min_f1,
            )
        except RegressionDetected as exc:
            if notifier is not None:
                await notifier.notify(
                    exc,
                    dataset_name=dataset.name,
                    model=model,
                    report_path=summary.report_path,
                )
            raise
    return summary


@dataclass(slots=True)
class _SampleRun:
    """Per-sample outputs; the only source of truth for aggregate metrics."""

    result: CurationBenchmarkResult
    score: CurationScore
    tokens: int
    duration_seconds: float
    flagged_ids: list[str] = field(default_factory=list)
    injection_count: int = 0
    pii_count: int = 0


async def _run_sample(
    provider: AIProvider,
    sample: CurationSample,
    target_count: int,
    safety: SafetyGate,
    collector: TraceCollector,
    meter: MetricsRegistry,
) -> _SampleRun:
    """Run one sample end to end and return its own counters and score.

    The harness plans exactly one step per sample: the curate LLM call.
    Safety checks are gray mode: violations are counted and flagged, never
    skipped or zeroed.
    """
    collector.start_sample(sample.id, ("curate",))

    injection_count = 0
    pii_count = 0
    flagged_ids: list[str] = []
    for candidate in sample.candidates:
        input_report = safety.check_input(
            {"title": candidate.title, "description": candidate.description}
        )
        if input_report.passed:
            continue
        if input_report.injection_detected:
            injection_count += 1
        if input_report.pii_detected:
            pii_count += 1
        flagged_ids.append(candidate.id)

    start = time.perf_counter()
    try:
        selected, response = await run_curation_with_response(provider, sample, target_count)
    except (ValueError, ProviderError) as first_error:
        # One malformed/unavailable output must not kill the whole run: retry
        # once, then score the sample 0 and keep going (P64.4, glm robustness).
        log.warning(
            "curator_output_retry",
            sample_id=sample.id,
            error=type(first_error).__name__,
            detail=str(first_error)[:200],
        )
        try:
            selected, response = await run_curation_with_response(provider, sample, target_count)
        except (ValueError, ProviderError) as second_error:
            log.warning(
                "curator_output_dropped",
                sample_id=sample.id,
                error=type(second_error).__name__,
                detail=str(second_error)[:200],
            )
            duration_seconds = time.perf_counter() - start
            score = score_curation(set(), set(sample.expected_selected_ids))
            result = CurationBenchmarkResult(
                sample_id=sample.id,
                precision=score.precision,
                recall=score.recall,
                f1=score.f1,
                passed=score.passed,
            )
            meter.record_llm_call(tokens=0, duration_seconds=duration_seconds)
            return _SampleRun(
                result=result,
                score=score,
                tokens=0,
                duration_seconds=duration_seconds,
                flagged_ids=flagged_ids,
                injection_count=injection_count,
                pii_count=pii_count,
            )
    duration_seconds = time.perf_counter() - start

    output_report = safety.check_output(response.content)
    if output_report.injection_detected:
        injection_count += 1
    if output_report.pii_detected:
        pii_count += 1

    usage = response.usage
    tokens = usage.input_tokens + usage.output_tokens if usage is not None else 0
    meter.record_llm_call(tokens=tokens, duration_seconds=duration_seconds)

    score = score_curation(selected, set(sample.expected_selected_ids))
    result = CurationBenchmarkResult(
        sample_id=sample.id,
        precision=score.precision,
        recall=score.recall,
        f1=score.f1,
        passed=score.passed,
    )
    collector.record_step_complete(sample.id, "curate")
    collector.end_sample(sample.id)
    return _SampleRun(
        result=result,
        score=score,
        tokens=tokens,
        duration_seconds=duration_seconds,
        flagged_ids=flagged_ids,
        injection_count=injection_count,
        pii_count=pii_count,
    )


def _project_candidate(candidate: object) -> dict[str, object]:
    """Project one candidate to the same compact shape used by daily_digest."""
    candidate_id = getattr(candidate, "id", None)
    title = getattr(candidate, "title", None)
    description = getattr(candidate, "description", None)
    url = getattr(candidate, "url", None)
    source = getattr(candidate, "source", None)
    if not all(isinstance(value, str) for value in (candidate_id, title, description, url, source)):
        raise ValueError("invalid curation candidate")
    candidate_id = cast(str, candidate_id)
    title = cast(str, title)
    description = cast(str, description)
    url = cast(str, url)
    source = cast(str, source)
    projected: dict[str, object] = {
        "id": candidate_id,
        "title": title,
        "summary": description[:CURATE_SUMMARY_CHAR_LIMIT],
        "url": url,
        "source": source,
    }
    if not str(projected["summary"]).strip():
        projected["summary"] = fallback_summary(title)
    if source == "github_trending":
        projected["g"] = True
    # Static curation fixtures do not model the runtime freshness fallback metadata.
    # The fallback branch is covered by daily_digest projection tests instead.
    return projected


def _selected_ids(content: str) -> set[str]:
    """Parse a strict or embedded JSON array and extract selected IDs."""
    decoded: object
    try:
        decoded = json.loads(content)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        decoded = None
        for index, character in enumerate(content):
            if character != "[":
                continue
            try:
                decoded, _ = decoder.raw_decode(content[index:])
                break
            except json.JSONDecodeError:
                continue
        if decoded is None:
            raise ValueError("curator output must contain a JSON array") from None
    if not isinstance(decoded, list) or not all(isinstance(item, Mapping) for item in decoded):
        raise ValueError("curator output must be a JSON array of objects")
    selected: set[str] = set()
    for item in decoded:
        value = item.get("id")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("curator output item id must be a non-empty string")
        selected.add(value)
    return selected


def _safe_pct(numerator: float, denominator: float) -> float:
    """Return numerator / denominator, defaulting to 0.0 when denominator is zero."""
    return numerator / denominator if denominator else 0.0


def _percentile(samples: list[float], quantile: float) -> float:
    """Nearest-rank percentile of latency samples (seconds)."""
    if not samples:
        return 0.0
    ordered = sorted(samples)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[rank - 1]


def _summarize(
    dataset_name: str,
    results: list[tuple[CurationBenchmarkResult, CurationScore]],
    collector: TraceCollector,
    *,
    injection_count: int,
    pii_count: int,
    total_tokens: int,
    latencies: list[float],
    wall_clock_seconds: float,
) -> CurationBenchmarkSummary:
    """Aggregate sample scores together with process, efficiency, and safety metrics."""
    total = len(results)
    avg_precision = _safe_pct(sum(result.precision for result, _ in results), total)
    avg_recall = _safe_pct(sum(result.recall for result, _ in results), total)
    avg_f1 = _safe_pct(sum(result.f1 for result, _ in results), total)
    step_success, avg_steps, plan_match, retry_rate = collector.aggregate()
    return CurationBenchmarkSummary(
        dataset_name=dataset_name,
        total=total,
        passed=sum(1 for result, _ in results if result.passed),
        failed=sum(1 for result, _ in results if not result.passed),
        avg_precision=avg_precision,
        avg_recall=avg_recall,
        avg_f1=avg_f1,
        overall=avg_f1,
        step_success_rate=step_success,
        avg_steps_per_sample=avg_steps,
        plan_match_rate=plan_match,
        retry_rate=retry_rate,
        avg_tokens=round(total_tokens / total) if total else 0,
        p50_latency_ms=_percentile(latencies, 0.50) * 1000.0,
        p95_latency_ms=_percentile(latencies, 0.95) * 1000.0,
        # The curation harness invokes no tools, so this stays a real zero.
        avg_tool_calls=0,
        wall_clock_seconds=wall_clock_seconds,
        injection_blocked=injection_count,
        pii_violations=pii_count,
        permission_violations=0,
    )


def _write_report(
    dataset: CurationDataset,
    results: list[tuple[CurationBenchmarkResult, CurationScore]],
    summary: CurationBenchmarkSummary,
    reports_dir: Path,
    safety_flags: dict[str, list[str]] | None = None,
) -> Path:
    """Write one human-readable Markdown report for a benchmark run."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    report_path = reports_dir / f"{dataset.name}_{timestamp}.md"
    lines = [
        f"# 策展 Precision/Recall 报告 — {dataset.name}",
        "",
        f"- 样本数: {summary.total} (通过 {summary.passed}, 失败 {summary.failed})",
        f"- 平均 Precision: {summary.avg_precision:.3f}",
        f"- 平均 Recall: {summary.avg_recall:.3f}",
        f"- **平均 F1: {summary.avg_f1:.3f}**",
        "",
        "## 过程层",
        f"- step_success_rate: {summary.step_success_rate:.3f}",
        f"- avg_steps_per_sample: {summary.avg_steps_per_sample:.3f}",
        f"- plan_match_rate: {summary.plan_match_rate:.3f}",
        f"- retry_rate: {summary.retry_rate:.3f}",
        "",
        "## 效率层",
        f"- avg_tokens: {summary.avg_tokens}",
        f"- p50_latency_ms: {summary.p50_latency_ms:.1f}",
        f"- p95_latency_ms: {summary.p95_latency_ms:.1f}",
        f"- wall_clock_seconds: {summary.wall_clock_seconds:.3f}",
        (
            f"- throughput_samples_per_second: "
            f"{_safe_pct(summary.total, summary.wall_clock_seconds):.3f}"
        ),
        f"- avg_tool_calls: {summary.avg_tool_calls} (策展链路无工具调用,真值 0)",
        "",
        "## 安全层 (P64.1 灰度: 只记录, 不阻断)",
        f"- injection_blocked (检测数, 未阻断): {summary.injection_blocked}",
        f"- pii_violations: {summary.pii_violations}",
        f"- permission_violations: {summary.permission_violations} (策展链路无工具调用)",
    ]
    if safety_flags:
        lines.append("")
        lines.append("### 灰度标记的候选 (正常评分, 未阻断)")
        for sample_id, ids in safety_flags.items():
            lines.append(f"- {sample_id}: {', '.join(ids)}")
    lines.extend(
        [
            "",
            "| ID | Precision | Recall | F1 | 状态 | 选择 |",
            "|---|---:|---:|---:|---|---|",
        ]
    )
    for result, score in results:
        status = "通过" if result.passed else "失败"
        selection = (
            f"sel={','.join(sorted(score.selected_ids))};"
            f"exp={','.join(sorted(score.expected_selected_ids))}"
        )
        lines.append(
            f"| {result.sample_id} | {result.precision:.3f} | {result.recall:.3f} | "
            f"{result.f1:.3f} | {status} | {selection} |"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def _baseline_dim(payload: Mapping[str, object], key: str) -> float:
    """Read one numeric baseline dimension, treating non-numeric values as 0.0."""
    value = payload.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _archive_baseline(baseline_path: Path) -> Path:
    """Copy the current baseline to a timestamped snapshot before overwriting.

    The drift detector (P64.2 T12) reads these snapshots to build trend tables.
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    archive = baseline_path.parent / f"{baseline_path.stem}_{timestamp}.json"
    suffix = 1
    while archive.exists():
        archive = baseline_path.parent / f"{baseline_path.stem}_{timestamp}-{suffix}.json"
        suffix += 1
    shutil.copyfile(baseline_path, archive)
    return archive


@dataclass(frozen=True, slots=True)
class _GateViolation:
    """One baseline comparison that failed with serializable audit metadata."""

    dimension: str
    baseline: float
    current: float
    threshold: float


def _collect_gate_violations(
    summary: CurationBenchmarkSummary,
    payload: Mapping[str, object],
    threshold: float,
    thresholds: MetricThresholds,
    phase_min_f1: float | None,
) -> list[_GateViolation]:
    """Collect every failed comparison without mutating a baseline or raising."""
    violations: list[_GateViolation] = []
    baseline_f1 = _baseline_dim(payload, "avg_f1") or _baseline_dim(payload, "overall")
    if baseline_f1 - summary.avg_f1 > threshold:
        violations.append(_GateViolation("f1", baseline_f1, summary.avg_f1, threshold))

    for name, current in (
        ("precision", summary.avg_precision),
        ("recall", summary.avg_recall),
        ("step_success_rate", summary.step_success_rate),
    ):
        baseline_key = f"avg_{name}" if name in {"precision", "recall"} else name
        if baseline_key not in payload:
            continue
        baseline = _baseline_dim(payload, baseline_key)
        if baseline - current > threshold:
            violations.append(_GateViolation(name, baseline, current, threshold))

    if summary.retry_rate > thresholds.max_retry_rate:
        violations.append(
            _GateViolation(
                "retry_rate",
                thresholds.max_retry_rate,
                summary.retry_rate,
                thresholds.max_retry_rate,
            )
        )

    baseline_tokens = _baseline_dim(payload, "avg_tokens")
    if baseline_tokens > 0:
        token_increase = (summary.avg_tokens - baseline_tokens) / baseline_tokens
        if token_increase > thresholds.token_increase_ratio:
            violations.append(
                _GateViolation(
                    "avg_tokens_ratio",
                    baseline_tokens,
                    float(summary.avg_tokens),
                    thresholds.token_increase_ratio,
                )
            )

    baseline_p95 = _baseline_dim(payload, "p95_latency_ms")
    if baseline_p95 > 0:
        latency_increase = (summary.p95_latency_ms - baseline_p95) / baseline_p95
        if latency_increase > thresholds.latency_p95_increase_ratio:
            violations.append(
                _GateViolation(
                    "p95_latency_ratio",
                    baseline_p95,
                    summary.p95_latency_ms,
                    thresholds.latency_p95_increase_ratio,
                )
            )

    if (
        thresholds.max_tokens_per_sample is not None
        and summary.avg_tokens > thresholds.max_tokens_per_sample
    ):
        violations.append(
            _GateViolation(
                "avg_tokens_cap",
                float(thresholds.max_tokens_per_sample),
                float(summary.avg_tokens),
                float(thresholds.max_tokens_per_sample),
            )
        )

    if (
        thresholds.max_p95_latency_ms is not None
        and summary.p95_latency_ms > thresholds.max_p95_latency_ms
    ):
        violations.append(
            _GateViolation(
                "p95_latency_cap",
                float(thresholds.max_p95_latency_ms),
                summary.p95_latency_ms,
                float(thresholds.max_p95_latency_ms),
            )
        )

    if phase_min_f1 is not None and summary.avg_f1 < phase_min_f1:
        violations.append(_GateViolation("phase_f1", phase_min_f1, summary.avg_f1, phase_min_f1))
    return violations


def _check_and_write_baseline(
    summary: CurationBenchmarkSummary,
    baseline_path: Path,
    threshold: float,
    thresholds: MetricThresholds,
    *,
    ledger_path: Path | None = None,
    concurrency: int = 1,
    model: str = "",
    phase_min_f1: float | None = None,
) -> None:
    """Gate a summary, ledger every rejection, then archive and replace accepted baselines."""
    if baseline_path.exists():
        try:
            payload = json.loads(baseline_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("baseline must be a JSON object")
            baseline_value = payload.get("avg_f1", payload.get("overall"))
            if not isinstance(baseline_value, (int, float)) or isinstance(baseline_value, bool):
                raise ValueError("baseline avg_f1 must be numeric")
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid curation benchmark baseline {baseline_path}: {exc}") from exc

        violations = _collect_gate_violations(summary, payload, threshold, thresholds, phase_min_f1)
        if violations:
            if ledger_path is not None:
                append_rejected(
                    RejectedRun(
                        timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
                        report_path=summary.report_path,
                        precision=summary.avg_precision,
                        recall=summary.avg_recall,
                        f1=summary.avg_f1,
                        avg_tokens=summary.avg_tokens,
                        p95_latency_ms=summary.p95_latency_ms,
                        wall_clock_seconds=summary.wall_clock_seconds,
                        rejected_dimensions=[violation.dimension for violation in violations],
                        concurrency=concurrency,
                        model=model,
                    ),
                    ledger_path,
                )
            first = violations[0]
            raise RegressionDetected(
                first.baseline,
                first.current,
                first.threshold,
                dimension=first.dimension,
                violations=tuple(violation.dimension for violation in violations),
                report_path=summary.report_path,
            )

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    if baseline_path.exists():
        _archive_baseline(baseline_path)
    baseline_path.write_text(
        json.dumps(asdict(summary), ensure_ascii=False, indent=2), encoding="utf-8"
    )


__all__ = [
    "CurationBenchmarkResult",
    "CurationBenchmarkSummary",
    "EvalMetrics",
    "MetricThresholds",
    "RegressionDetected",
    "SafetyGate",
    "SafetyReport",
    "TraceCollector",
    "run_curation",
    "run_curation_benchmark",
    "run_curation_with_response",
]
