"""Run real-curator curation benchmarks with deterministic ground-truth scoring."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from multiscribe_agent.agents.pipelines.prompts import CURATE_PROMPT
from multiscribe_agent.domain.models import AIMessage
from multiscribe_agent.eval.benchmark import RegressionDetected
from multiscribe_agent.eval.curation_dataset import CurationDataset, CurationSample
from multiscribe_agent.eval.curation_scorer import CurationScore, score_curation
from multiscribe_agent.llm.provider import AIProvider

CURATION_SYSTEM_INSTRUCTION = "You are a careful Chinese AI news curation assistant."


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


async def run_curation(provider: AIProvider, sample: CurationSample, target_count: int) -> set[str]:
    """Ask the configured curator to select candidate IDs for one sample."""
    if target_count < 1:
        raise ValueError("target_count must be positive")
    items = [_project_candidate(candidate) for candidate in sample.candidates]
    prompt = CURATE_PROMPT.format(
        items=json.dumps(items, ensure_ascii=False, sort_keys=True),
        feedback="无",
        target_count=target_count,
    )
    response = await provider.generate(
        [AIMessage(role="user", content=prompt)],
        system_instruction=CURATION_SYSTEM_INSTRUCTION,
    )
    return _selected_ids(response.content)


async def run_curation_benchmark(
    provider: AIProvider,
    dataset: CurationDataset,
    reports_dir: Path,
    baseline_path: Path | None = None,
    threshold: float = 0.10,
    target_count: int = 12,
) -> CurationBenchmarkSummary:
    """Run all samples, write a Markdown report, and detect F1 regression."""
    if not threshold >= 0.0:
        raise ValueError("threshold must not be negative")
    results: list[tuple[CurationBenchmarkResult, CurationScore]] = []
    for sample in dataset.samples:
        selected = await run_curation(provider, sample, target_count)
        score = score_curation(selected, set(sample.expected_selected_ids))
        results.append(
            (
                CurationBenchmarkResult(
                    sample_id=sample.id,
                    precision=score.precision,
                    recall=score.recall,
                    f1=score.f1,
                    passed=score.passed,
                ),
                score,
            )
        )

    summary = _summarize(dataset.name, results)
    report_path = _write_report(dataset, results, summary, reports_dir)
    summary = CurationBenchmarkSummary(**{**asdict(summary), "report_path": str(report_path)})
    if baseline_path is not None:
        _check_and_write_baseline(summary, baseline_path, threshold)
    return summary


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
        "summary": description[:150],
        "url": url,
        "source": source,
    }
    if source == "github_trending":
        projected["g"] = True
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


def _summarize(
    dataset_name: str, results: list[tuple[CurationBenchmarkResult, CurationScore]]
) -> CurationBenchmarkSummary:
    """Aggregate sample scores without weighting by candidate-pool size."""
    total = len(results)
    avg_precision = sum(result.precision for result, _ in results) / total
    avg_recall = sum(result.recall for result, _ in results) / total
    avg_f1 = sum(result.f1 for result, _ in results) / total
    return CurationBenchmarkSummary(
        dataset_name=dataset_name,
        total=total,
        passed=sum(1 for result, _ in results if result.passed),
        failed=sum(1 for result, _ in results if not result.passed),
        avg_precision=avg_precision,
        avg_recall=avg_recall,
        avg_f1=avg_f1,
        overall=avg_f1,
    )


def _write_report(
    dataset: CurationDataset,
    results: list[tuple[CurationBenchmarkResult, CurationScore]],
    summary: CurationBenchmarkSummary,
    reports_dir: Path,
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
        "| ID | Precision | Recall | F1 | 状态 |",
        "|---|---:|---:|---:|---|",
    ]
    for result, _ in results:
        status = "通过" if result.passed else "失败"
        lines.append(
            f"| {result.sample_id} | {result.precision:.3f} | {result.recall:.3f} | "
            f"{result.f1:.3f} | {status} |"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def _check_and_write_baseline(
    summary: CurationBenchmarkSummary, baseline_path: Path, threshold: float
) -> None:
    """Compare average F1 to a previous baseline and persist the new summary."""
    if baseline_path.exists():
        try:
            payload = json.loads(baseline_path.read_text(encoding="utf-8"))
            baseline_value = payload.get("avg_f1", payload.get("overall"))
            if not isinstance(baseline_value, (int, float)) or isinstance(baseline_value, bool):
                raise ValueError("baseline avg_f1 must be numeric")
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid curation benchmark baseline {baseline_path}: {exc}") from exc
        if baseline_value - summary.avg_f1 > threshold:
            raise RegressionDetected(float(baseline_value), summary.avg_f1, threshold)
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(asdict(summary), ensure_ascii=False, indent=2), encoding="utf-8"
    )


__all__ = [
    "CurationBenchmarkResult",
    "CurationBenchmarkSummary",
    "RegressionDetected",
    "run_curation",
    "run_curation_benchmark",
]
