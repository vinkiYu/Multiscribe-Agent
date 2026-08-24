"""Render the baseline trend table and drift alerts (P64.2 T12)."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from multiscribe_agent.eval.drift import DriftDetector, load_snapshots


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baselines", type=Path, default=Path("data/eval/baselines"))
    parser.add_argument("--out", type=Path, default=Path("data/eval/reports"))
    args = parser.parse_args()

    points = load_snapshots(args.baselines)
    if not points:
        raise SystemExit(f"no baseline snapshots under {args.baselines}")
    alerts = DriftDetector().detect(points)
    markdown = DriftDetector().render_trend(points, alerts)
    args.out.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = args.out / f"drift_{timestamp}.md"
    target.write_text(markdown, encoding="utf-8")
    print(f"rounds={len(points)} alerts={len(alerts)}")
    print(target)


if __name__ == "__main__":
    main()
