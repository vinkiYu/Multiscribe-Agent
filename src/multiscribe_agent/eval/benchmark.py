"""Run evaluations across a dataset, detect regressions, and emit reports."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from multiscribe_agent.eval.dataset import Dataset
from multiscribe_agent.eval.evaluator import EvaluationResult, JudgeError, evaluate_sample
from multiscribe_agent.llm.provider import AIProvider


class RegressionDetected(RuntimeError):
    """Raised when overall score drops more than the regression threshold."""

    def __init__(self, baseline: float, current: float, threshold: float) -> None:
        super().__init__(
            f"Regression: {baseline:.2f} → {current:.2f} "
            f"(drop {baseline - current:.2f} > {threshold:.2f})"
        )
        self.baseline = baseline
        self.current = current
        self.threshold = threshold


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    """Aggregate result persisted as the next benchmark baseline."""

    dataset_name: str
    total: int
    passed: int
    failed: int
    avg_summary: float
    avg_relevance: float
    avg_stability: float
    overall: float


async def run_benchmark(
    provider: AIProvider,
    dataset: Dataset,
    preferred_tags: list[str],
    reports_dir: Path,
    baseline_path: Path | None = None,
    regression_threshold: float = 0.10,
) -> BenchmarkSummary:
    """Evaluate all samples, write a Markdown report, and update the baseline."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    results: list[EvaluationResult] = []
    for sample in dataset.samples:
        try:
            result = await evaluate_sample(
                provider,
                sample.id,
                Path(sample.input_path),
                preferred_tags,
            )
        except JudgeError as exc:
            raise JudgeError(f"Sample {sample.id} failed: {exc}") from exc
        results.append(result)

    summary = _summarize(dataset, results)
    _write_report(dataset, results, summary, reports_dir)

    if baseline_path is not None:
        if baseline_path.exists():
            try:
                baseline = BenchmarkSummary(**json.loads(baseline_path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid benchmark baseline {baseline_path}: {exc}") from exc
            if (baseline.overall - summary.overall) > regression_threshold:
                raise RegressionDetected(baseline.overall, summary.overall, regression_threshold)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(asdict(summary), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return summary


def _summarize(dataset: Dataset, results: list[EvaluationResult]) -> BenchmarkSummary:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    avg_summary = sum(result.summary.overall for result in results) / total
    avg_relevance = sum(result.relevance.relevance for result in results) / total
    avg_stability = sum(result.stability.stability for result in results) / total
    overall = (avg_summary + avg_relevance + avg_stability) / 3
    return BenchmarkSummary(
        dataset_name=dataset.name,
        total=total,
        passed=passed,
        failed=total - passed,
        avg_summary=avg_summary,
        avg_relevance=avg_relevance,
        avg_stability=avg_stability,
        overall=overall,
    )


def _write_report(
    dataset: Dataset,
    results: list[EvaluationResult],
    summary: BenchmarkSummary,
    reports_dir: Path,
) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    report_path = reports_dir / f"{dataset.name}_{timestamp}.md"
    lines = [
        f"# 评估报告 — {dataset.name}",
        "",
        f"- 生成时间: {timestamp}",
        f"- 样本数: {summary.total} (通过 {summary.passed}, 失败 {summary.failed})",
        f"- 平均摘要质量: {summary.avg_summary:.2f} / 10",
        f"- 平均相关性: {summary.avg_relevance:.2f} / 10",
        f"- 平均稳定性: {summary.avg_stability:.2f} / 10",
        f"- **总体得分: {summary.overall:.2f} / 10**",
        "",
        "## 样本明细",
        "",
        "| ID | 摘要 | 相关 | 稳定 | 状态 |",
        "|----|------|------|------|------|",
    ]
    for result in results:
        status = "通过" if result.passed else "失败"
        lines.append(
            f"| {result.sample_id} | {result.summary.overall} | "
            f"{result.relevance.relevance} | {result.stability.stability} | {status} |"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path
