"""Tests for the P64.3 rejected-run audit ledger."""

from __future__ import annotations

from pathlib import Path

import pytest

from multiscribe_agent.eval.ledger import RejectedRun, append_rejected, load_ledger


def _run() -> RejectedRun:
    return RejectedRun(
        timestamp="2026-08-15T08:00:00+00:00",
        report_path="data/eval/reports/curation-recall.md",
        precision=0.8,
        recall=0.78,
        f1=0.79,
        avg_tokens=7500,
        p95_latency_ms=18000.0,
        wall_clock_seconds=240.0,
        rejected_dimensions=["precision", "phase_f1"],
        concurrency=4,
        model="gpt-5.4",
    )


def test_load_missing_ledger_returns_empty(tmp_path: Path) -> None:
    assert load_ledger(tmp_path / "missing.jsonl") == []


def test_append_and_load_round_trip(tmp_path: Path) -> None:
    ledger = tmp_path / "rejected.jsonl"
    append_rejected(_run(), ledger)
    append_rejected(_run(), ledger)

    records = load_ledger(ledger)

    assert records == [_run(), _run()]
    assert len(ledger.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_load_rejects_corrupt_line_with_line_number(tmp_path: Path) -> None:
    ledger = tmp_path / "rejected.jsonl"
    ledger.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"rejected\.jsonl:1"):
        load_ledger(ledger)
