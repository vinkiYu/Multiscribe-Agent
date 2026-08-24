"""Run or preview the P64.3 six-step weekly evaluation pipeline."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from multiscribe_agent.cli import _resolve_eval_provider
from multiscribe_agent.config import get_settings
from multiscribe_agent.eval.orchestrator.week_pipeline import WeekPipeline
from multiscribe_agent.observability.notifier import RegressionNotifier


def _notifier() -> RegressionNotifier:
    settings = get_settings()
    raw = settings.eval_regression_alert_targets
    targets = [item.strip() for item in raw.split(",") if item.strip()]
    options = {publisher.id: publisher.config for publisher in settings.publishers}
    return RegressionNotifier(targets=targets, publisher_options=options)


async def run(dry_run: bool) -> None:
    """Compose the pipeline from settings and print its step statuses."""
    settings = get_settings()
    provider = None if dry_run else _resolve_eval_provider(settings)
    pipeline = WeekPipeline(
        provider=provider,
        model=settings.default_curation_model,
        dataset_path=Path("data/eval/datasets/curation_recall.yaml"),
        fixtures_dir=Path("tests/eval/fixtures"),
        reports_dir=Path("data/eval/reports"),
        baselines_dir=Path("data/eval/baselines"),
        baseline_path=Path("data/eval/baselines/curation_recall.json"),
        bad_cases_dir=Path("data/eval/bad_cases"),
        ledger_path=Path("data/eval/ledgers/rejected_runs.jsonl"),
        traces_dir=Path("data/eval/traces"),
        disputes_dir=Path("data/eval/label_disputes"),
        notifier=_notifier(),
    )
    report = await pipeline.run(dry_run=dry_run)
    for step, result in report.steps.items():
        print(f"{step}: {result.status} — {result.detail}")
    print(f"pipeline_succeeded={report.succeeded} dry_run={report.dry_run}")


def main() -> None:
    """Parse mode and execute the pipeline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="read-only preview; never calls LLMs"
    )
    args = parser.parse_args()
    asyncio.run(run(args.dry_run))


if __name__ == "__main__":
    main()
