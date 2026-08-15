"""Append-only audit ledger for rejected evaluation runs (P64.3 P1)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RejectedRun:
    """One benchmark run rejected before it could replace a protected baseline."""

    timestamp: str
    report_path: str
    precision: float
    recall: float
    f1: float
    avg_tokens: int
    p95_latency_ms: float
    wall_clock_seconds: float
    rejected_dimensions: list[str]
    concurrency: int
    model: str


def append_rejected(run: RejectedRun, ledger_path: Path) -> None:
    """Append one JSONL audit record without rewriting prior rejection history."""
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(asdict(run), ensure_ascii=False) + "\n")


def load_ledger(ledger_path: Path) -> list[RejectedRun]:
    """Load an audit ledger, rejecting malformed records with line context."""
    if not ledger_path.exists():
        return []
    records: list[RejectedRun] = []
    for line_number, line in enumerate(ledger_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("record must be a JSON object")
            records.append(_record_from_payload(payload))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Invalid rejected-run ledger {ledger_path}:{line_number}: {exc}"
            ) from exc
    return records


def _record_from_payload(payload: dict[str, object]) -> RejectedRun:
    def text(name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        return value

    def number(name: str) -> float:
        value = payload.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{name} must be numeric")
        return float(value)

    def integer(name: str) -> int:
        value = payload.get(name)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{name} must be an integer")
        return value

    dimensions = payload.get("rejected_dimensions")
    if not isinstance(dimensions, list) or not all(isinstance(item, str) for item in dimensions):
        raise ValueError("rejected_dimensions must be a list of strings")
    return RejectedRun(
        timestamp=text("timestamp"),
        report_path=text("report_path"),
        precision=number("precision"),
        recall=number("recall"),
        f1=number("f1"),
        avg_tokens=integer("avg_tokens"),
        p95_latency_ms=number("p95_latency_ms"),
        wall_clock_seconds=number("wall_clock_seconds"),
        rejected_dimensions=list(dimensions),
        concurrency=integer("concurrency"),
        model=text("model"),
    )


__all__ = ["RejectedRun", "append_rejected", "load_ledger"]
