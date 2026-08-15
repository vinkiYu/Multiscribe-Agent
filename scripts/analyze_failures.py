"""Analyze benchmark failures into the five-class report (P64.2 T10)."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from multiscribe_agent.eval.analysis import analyze_failures, render_analysis


def latest_report(reports_dir: Path) -> Path:
    reports = sorted(reports_dir.glob("curation-recall_*.md"))
    if not reports:
        raise SystemExit(f"no curation-recall report under {reports_dir}")
    return reports[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=None, help="report md (default: latest)")
    parser.add_argument("--fixtures", type=Path, default=Path("tests/eval/fixtures"))
    parser.add_argument("--threshold", type=float, default=0.7)
    parser.add_argument("--out", type=Path, default=Path("data/eval/reports"))
    args = parser.parse_args()

    report = args.report or latest_report(args.out)
    analysis = analyze_failures(report, args.fixtures, threshold=args.threshold)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = args.out / f"failure-analysis_{timestamp}.md"
    target.write_text(render_analysis(analysis), encoding="utf-8")
    print(f"failed={analysis.total_failed} distribution={analysis.distribution}")
    print(target)


if __name__ == "__main__":
    main()
