"""Six-step weekly evaluation pipeline (P64.3 T13).

The pipeline is deliberately sequential because later steps consume explicit
artifacts from earlier ones. Its dry-run mode is a strict preview: it reads
existing reports and fixtures but never calls an LLM, writes an artifact,
updates a baseline, appends a ledger, creates a cache, or sends a notification.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from multiscribe_agent.eval.analysis import analyze_failures, render_analysis
from multiscribe_agent.eval.benchmark import RegressionDetected
from multiscribe_agent.eval.cleaner.dedup_hasher import DedupHasher
from multiscribe_agent.eval.cleaner.label_auditor import LabelAuditor
from multiscribe_agent.eval.clustering import EMBEDDING_BACKEND, kmeans, tfidf_vectors
from multiscribe_agent.eval.collector.bad_case import BadCaseCollector, BadCaseRecord
from multiscribe_agent.eval.collector.trace_sink import TraceSink
from multiscribe_agent.eval.curation_benchmark import run_curation_benchmark
from multiscribe_agent.eval.curation_dataset import load_curation_dataset
from multiscribe_agent.eval.drift import DriftDetector, load_snapshots
from multiscribe_agent.eval.orchestrator.states import (
    PipelineReport,
    PipelineStep,
    PipelineStepResult,
    StepStatus,
)
from multiscribe_agent.llm.provider import AIProvider
from multiscribe_agent.observability.notifier import RegressionNotifier


class WeekPipeline:
    """Run collect -> clean -> bench -> gate -> analyze -> feedback once."""

    def __init__(
        self,
        *,
        provider: AIProvider | None,
        model: str,
        dataset_path: Path,
        fixtures_dir: Path,
        reports_dir: Path,
        baselines_dir: Path,
        baseline_path: Path,
        bad_cases_dir: Path,
        ledger_path: Path,
        traces_dir: Path,
        disputes_dir: Path,
        notifier: RegressionNotifier | None = None,
        concurrency: int = 4,
        phase_min_f1: float = 0.80,
    ) -> None:
        self._provider = provider
        self._model = model
        self._dataset_path = dataset_path
        self._fixtures_dir = fixtures_dir
        self._reports_dir = reports_dir
        self._baselines_dir = baselines_dir
        self._baseline_path = baseline_path
        self._bad_cases_dir = bad_cases_dir
        self._ledger_path = ledger_path
        self._traces_dir = traces_dir
        self._disputes_dir = disputes_dir
        self._notifier = notifier
        self._concurrency = concurrency
        self._phase_min_f1 = phase_min_f1

    async def run(self, *, dry_run: bool = False) -> PipelineReport:
        """Run every stage, preserving a readable result even when the gate rejects."""
        report = PipelineReport(
            run_id=uuid4().hex,
            started_at=datetime.now(UTC),
            dry_run=dry_run,
            steps={step: PipelineStepResult(step, StepStatus.PENDING) for step in PipelineStep},
        )
        source_report = self._latest_report()
        if source_report is None:
            self._fail_and_skip(report, PipelineStep.COLLECT, "no existing curation report")
            report.finished_at = datetime.now(UTC)
            return report

        collector = BadCaseCollector(self._fixtures_dir)
        try:
            bad_cases = collector.collect(source_report)
            collect_paths: tuple[str, ...] = ()
            if not dry_run:
                collect_paths = (str(collector.write(bad_cases, self._bad_cases_dir)),)
            self._succeed(
                report,
                PipelineStep.COLLECT,
                f"{len(bad_cases)} failed samples from {source_report.name}",
                collect_paths,
            )
        except Exception as exc:
            self._fail_and_skip(report, PipelineStep.COLLECT, str(exc))
            report.finished_at = datetime.now(UTC)
            return report

        try:
            dataset = load_curation_dataset(self._dataset_path)
            duplicates = DedupHasher().find_duplicates(self._load_fixture_candidates())
            clean_paths: tuple[str, ...] = ()
            audit_detail = "audit planned only"
            if not dry_run:
                if self._provider is None:
                    raise ValueError("real pipeline requires a provider for label audit")
                auditor = LabelAuditor(self._provider)
                disputes = await auditor.audit(dataset.samples, ratio=0.1)
                clean_paths = (str(auditor.write(disputes, self._disputes_dir)),)
                audit_detail = f"{len(disputes)} label disputes"
            self._succeed(
                report,
                PipelineStep.CLEAN,
                f"{len(duplicates)} duplicate groups; {audit_detail}",
                clean_paths,
            )
        except Exception as exc:
            self._fail_and_skip(report, PipelineStep.CLEAN, str(exc))
            report.finished_at = datetime.now(UTC)
            return report

        benchmark_report = source_report
        if dry_run:
            self._succeed(
                report,
                PipelineStep.BENCH,
                ("planned benchmark; dry-run made no LLM or filesystem call"),
            )
            self._skip(report, PipelineStep.GATE, "dry-run did not evaluate or promote a baseline")
        else:
            if self._provider is None:
                self._fail_and_skip(report, PipelineStep.BENCH, "real pipeline requires a provider")
                report.finished_at = datetime.now(UTC)
                return report
            try:
                summary = await run_curation_benchmark(
                    self._provider,
                    dataset,
                    self._reports_dir,
                    baseline_path=self._baseline_path,
                    threshold=0.05,
                    target_count=12,
                    trace_sink=TraceSink(self._traces_dir),
                    ledger_path=self._ledger_path,
                    model=self._model,
                    phase_min_f1=self._phase_min_f1,
                    notifier=self._notifier,
                    concurrency=self._concurrency,
                )
                benchmark_report = Path(summary.report_path)
                self._succeed(
                    report,
                    PipelineStep.BENCH,
                    (f"F1={summary.avg_f1:.3f}, wall={summary.wall_clock_seconds:.3f}s"),
                    (summary.report_path,),
                )
                self._succeed(report, PipelineStep.GATE, "accepted; baseline promoted")
            except RegressionDetected as exc:
                rejected_report = (
                    Path(exc.report_path) if exc.report_path else self._latest_report()
                )
                benchmark_report = rejected_report or benchmark_report
                self._succeed(
                    report,
                    PipelineStep.BENCH,
                    f"report emitted before gate rejection: {benchmark_report}",
                    (str(benchmark_report),) if benchmark_report is not None else (),
                )
                self._fail(
                    report,
                    PipelineStep.GATE,
                    f"rejected dimensions: {', '.join(exc.violations)}",
                    ((str(self._ledger_path),) if self._ledger_path.exists() else ()),
                )

        if benchmark_report is None:
            self._fail_and_skip(report, PipelineStep.ANALYZE, "no report available for analysis")
            report.finished_at = datetime.now(UTC)
            return report

        try:
            analysis = analyze_failures(benchmark_report, self._fixtures_dir)
            analysis_markdown = render_analysis(analysis)
            cluster_markdown = self._render_clusters(collector.collect(benchmark_report), k=4)
            drift_points = load_snapshots(self._baselines_dir)
            detector = DriftDetector()
            drift_markdown = detector.render_trend(drift_points, detector.detect(drift_points))
            analysis_paths: tuple[str, ...] = ()
            if not dry_run:
                timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
                analysis_path = self._reports_dir / f"week-analysis_{timestamp}.md"
                analysis_path.parent.mkdir(parents=True, exist_ok=True)
                analysis_path.write_text(
                    "\n\n".join((analysis_markdown, cluster_markdown, drift_markdown)),
                    encoding="utf-8",
                )
                analysis_paths = (str(analysis_path),)
            self._succeed(
                report,
                PipelineStep.ANALYZE,
                (f"{analysis.total_failed} failures; {len(drift_points)} accepted baseline points"),
                analysis_paths,
            )
            report.feedback = self._feedback(analysis.distribution)
            self._succeed(
                report, PipelineStep.FEEDBACK, "human-review-only prompt advice generated"
            )
        except Exception as exc:
            self._fail_and_skip(report, PipelineStep.ANALYZE, str(exc))

        report.finished_at = datetime.now(UTC)
        if not dry_run:
            self._write_report(report)
        return report

    def _latest_report(self) -> Path | None:
        reports = sorted(self._reports_dir.glob("curation-recall_*.md"))
        return reports[-1] if reports else None

    def _load_fixture_candidates(self) -> dict[str, list[dict[str, str]]]:
        fixtures: dict[str, list[dict[str, str]]] = {}
        for path in sorted(self._fixtures_dir.glob("cr_*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
                raise ValueError(f"invalid fixture candidates: {path}")
            candidates = [
                candidate for candidate in payload["candidates"] if isinstance(candidate, dict)
            ]
            fixtures[path.stem.replace("_", "-")] = [
                {key: str(value) for key, value in candidate.items()} for candidate in candidates
            ]
        return fixtures

    @staticmethod
    def _render_clusters(records: list[BadCaseRecord], *, k: int) -> str:
        texts: list[str] = []
        for record in records:
            digest = record.candidates_digest.get("candidates", [])
            candidate_rows = (
                [candidate for candidate in digest if isinstance(candidate, dict)]
                if isinstance(digest, list)
                else []
            )
            titles = [str(candidate.get("title", "")) for candidate in candidate_rows]
            texts.append(" ".join(titles) or record.sample_id)
        vectors = tfidf_vectors(texts)
        clusters = kmeans(vectors, k=k)
        counts = Counter(clusters.labels)
        lines = [
            "## Pipeline TF-IDF Clusters",
            f"- backend: {EMBEDDING_BACKEND}",
            f"- k: {clusters.k}",
        ]
        lines.extend(
            f"- cluster {label + 1}: {count} samples" for label, count in sorted(counts.items())
        )
        return "\n".join(lines)

    @staticmethod
    def _feedback(distribution: dict[str, int]) -> str:
        mixed = distribution.get("mixed", 0)
        over_select = distribution.get("over_select", 0)
        miss = distribution.get("miss", 0)
        return (
            "Human review only — do not update prompts automatically. "
            f"Current failures: mixed={mixed}, over_select={over_select}, miss={miss}. "
            "Prioritize one failure class per prompt iteration "
            "and evaluate it against a stable control."
        )

    def _write_report(self, report: PipelineReport) -> Path:
        timestamp = report.started_at.strftime("%Y%m%d-%H%M%S")
        target = self._reports_dir / f"week-pipeline_{timestamp}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Week Pipeline Report",
            "",
            f"- run_id: {report.run_id}",
            f"- started_at: {report.started_at.isoformat()}",
            f"- finished_at: {report.finished_at.isoformat() if report.finished_at else ''}",
            f"- dry_run: {report.dry_run}",
            "",
            "| step | status | detail | artifacts |",
            "|---|---|---|---|",
        ]
        for step in PipelineStep:
            result = report.steps[step]
            artifacts = "<br>".join(result.artifact_paths)
            lines.append(f"| {step} | {result.status} | {result.detail} | {artifacts} |")
        lines.extend(("", "## Feedback", report.feedback))
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target

    @staticmethod
    def _succeed(
        report: PipelineReport,
        step: PipelineStep,
        detail: str,
        artifact_paths: tuple[str, ...] = (),
    ) -> None:
        report.steps[step] = PipelineStepResult(step, StepStatus.SUCCEEDED, detail, artifact_paths)

    @staticmethod
    def _fail(
        report: PipelineReport,
        step: PipelineStep,
        detail: str,
        artifact_paths: tuple[str, ...] = (),
    ) -> None:
        report.steps[step] = PipelineStepResult(step, StepStatus.FAILED, detail, artifact_paths)

    @classmethod
    def _skip(cls, report: PipelineReport, step: PipelineStep, detail: str) -> None:
        report.steps[step] = PipelineStepResult(step, StepStatus.SKIPPED, detail)

    @classmethod
    def _fail_and_skip(cls, report: PipelineReport, step: PipelineStep, detail: str) -> None:
        cls._fail(report, step, detail)
        ordered = list(PipelineStep)
        for later in ordered[ordered.index(step) + 1 :]:
            cls._skip(report, later, f"skipped after {step} failed")


__all__ = ["WeekPipeline"]
