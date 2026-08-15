"""Multi-round baseline drift detection (P64.2 T12).

Reads the archived baseline snapshots produced by
``curation_benchmark._archive_baseline`` plus the live baseline, renders a
trend table, and alerts when any dimension degrades monotonically for two
consecutive rounds.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_SNAPSHOT_RE = re.compile(r"^curation_recall(_\d{8}-\d{6}(-\d+)?)?\.json$")

# (key, header, higher_is_better); cost dims treat an increase as degradation.
DIMENSIONS: tuple[tuple[str, str, bool], ...] = (
    ("avg_f1", "F1", True),
    ("avg_precision", "Precision", True),
    ("avg_recall", "Recall", True),
    ("avg_tokens", "Tokens", False),
    ("p95_latency_ms", "p95(ms)", False),
)


@dataclass(frozen=True, slots=True)
class TrendPoint:
    """One baseline snapshot in the trend series."""

    label: str
    avg_f1: float
    avg_precision: float
    avg_recall: float
    avg_tokens: int
    p50_latency_ms: float
    p95_latency_ms: float


@dataclass(frozen=True, slots=True)
class DriftAlert:
    """A dimension that degraded for two consecutive rounds."""

    dimension: str
    from_value: float
    to_value: float
    round_labels: tuple[str, ...]


def load_snapshots(baselines_dir: Path) -> list[TrendPoint]:
    """Load the live baseline plus timestamped snapshots, oldest first.

    Snapshots sort by their embedded timestamp; the live ``curation_recall.json``
    always comes last regardless of name collisions.
    """
    points: list[tuple[str, dict[str, object]]] = []
    live: dict[str, object] | None = None
    for path in sorted(baselines_dir.glob("curation_recall*.json")):
        if not _SNAPSHOT_RE.match(path.name):
            continue
        payload: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
        if path.name == "curation_recall.json":
            live = payload
            continue
        stamp = path.stem.replace("curation_recall_", "")
        points.append((stamp, payload))
    ordered = [(_point_from(label, payload)) for label, payload in points]
    if live is not None:
        ordered.append(_point_from("current", live))
    return ordered


def _num(payload: dict[str, object], key: str, default: float = 0.0) -> float:
    value = payload.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def _point_from(label: str, payload: dict[str, object]) -> TrendPoint:
    return TrendPoint(
        label=label,
        avg_f1=_num(payload, "avg_f1") or _num(payload, "overall"),
        avg_precision=_num(payload, "avg_precision"),
        avg_recall=_num(payload, "avg_recall"),
        avg_tokens=int(_num(payload, "avg_tokens")),
        p50_latency_ms=_num(payload, "p50_latency_ms"),
        p95_latency_ms=_num(payload, "p95_latency_ms"),
    )


class DriftDetector:
    """Alert when any dimension moves the wrong way for two consecutive rounds."""

    def detect(self, points: list[TrendPoint]) -> list[DriftAlert]:
        alerts: list[DriftAlert] = []
        if len(points) < 3:
            return alerts
        for key, _, higher_is_better in DIMENSIONS:
            values = [getattr(point, key) for point in points]
            for index in range(2, len(values)):
                window = values[index - 2 : index + 1]
                # Cost dimensions read as missing (0) before P64.1; skip those.
                if not higher_is_better and 0.0 in window:
                    continue
                first, second, third = window
                degraded_twice = (
                    (second < first and third < second)
                    if higher_is_better
                    else (second > first and third > second)
                )
                if degraded_twice:
                    alerts.append(
                        DriftAlert(
                            dimension=key,
                            from_value=first,
                            to_value=third,
                            round_labels=tuple(p.label for p in points[index - 2 : index + 1]),
                        )
                    )
        return alerts

    def render_trend(self, points: list[TrendPoint], alerts: list[DriftAlert]) -> str:
        """Render the trend table plus alert lines as Markdown."""
        headers = ["轮次"] + [header for _, header, _ in DIMENSIONS]
        lines = [
            "# Curation Baseline 趋势",
            "",
            "| " + " | ".join(headers) + " |",
            "|" + "---:|" * len(headers),
        ]
        for point in points:
            lines.append(
                f"| {point.label} | {point.avg_f1:.3f} | {point.avg_precision:.3f} | "
                f"{point.avg_recall:.3f} | {point.avg_tokens} | {point.p95_latency_ms:.0f} |"
            )
        lines.append("")
        if alerts:
            lines.append("## 漂移告警 (连续 2 轮单向退化)")
            for alert in alerts:
                direction = "下降" if alert.from_value > alert.to_value else "上涨"
                lines.append(
                    f"- **{alert.dimension}** {direction}: {alert.from_value} → "
                    f"{alert.to_value} ({' → '.join(alert.round_labels)})"
                )
        else:
            lines.append("## 漂移告警")
            lines.append("- 无(没有维度连续 2 轮单向退化)")
        return "\n".join(lines) + "\n"


__all__ = ["DriftAlert", "DriftDetector", "TrendPoint", "load_snapshots"]
