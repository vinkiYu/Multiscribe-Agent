"""Tests for the P64.2 collector package and failure classification."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

from multiscribe_agent.eval.collector.bad_case import (
    BadCaseCollector,
    classify_row,
    parse_report_rows,
)
from multiscribe_agent.eval.collector.random_pool import SourceRow, build_pools
from multiscribe_agent.eval.collector.trace_sink import TraceSink
from multiscribe_agent.eval.failure_types import classify_failure
from multiscribe_agent.eval.trace_collector import SampleTrace

_REPORT = """# 策展 Precision/Recall 报告 — fixture

- 样本数: 3 (通过 1, 失败 2)

| ID | Precision | Recall | F1 | 状态 | 选择 |
|---|---:|---:|---:|---|---|
| cr-001 | 1.000 | 0.500 | 0.667 | 失败 | sel=cr-001-a1;exp=cr-001-a1,cr-001-a2,cr-001-a3 |
| cr-002 | 1.000 | 1.000 | 1.000 | 通过 | sel=cr-002-a1;exp=cr-002-a1 |
| cr-008 | 0.000 | 0.000 | 0.000 | 失败 | sel=;exp=cr-008-a1 |
"""


def _write_fixtures(tmp_path: Path) -> Path:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "cr_001.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {"id": f"cr-001-a{i}", "title": f"title {i}", "source": "rss"}
                    for i in (1, 2, 3)
                ],
                "expected_selected_ids": ["cr-001-a1", "cr-001-a2", "cr-001-a3"],
            }
        ),
        encoding="utf-8",
    )
    (fixtures / "cr_008.json").write_text(
        json.dumps(
            {
                "candidates": [{"id": "cr-008-a1", "title": "t", "source": "rss"}],
                "expected_selected_ids": ["cr-008-a1"],
            }
        ),
        encoding="utf-8",
    )
    return fixtures


def test_classify_failure_five_classes() -> None:
    """The five plan classes derive from exact diff sets."""
    assert classify_failure({"a", "b", "c"}, {"a"}) .failure_type == "miss"
    assert classify_failure({"a"}, {"a", "b", "c"}).failure_type == "over_select"
    assert classify_failure({"a", "b"}, {"b", "c"}).failure_type == "mixed"
    assert classify_failure({"a"}, set()).failure_type == "all_reject"
    assert classify_failure({"a"}, {"a", "b"}).failure_type == "boundary"
    assert classify_failure({"a"}, {"a"}) is None


def test_parse_report_rows_from_file(tmp_path: Path) -> None:
    report = tmp_path / "r.md"
    report.write_text(_REPORT, encoding="utf-8")
    rows = parse_report_rows(report)
    assert rows["cr-001"].selected_ids == frozenset({"cr-001-a1"})
    assert rows["cr-001"].expected_ids == frozenset(
        {"cr-001-a1", "cr-001-a2", "cr-001-a3"}
    )
    assert rows["cr-001"].f1 == 0.667
    assert classify_row(rows["cr-001"]) == "miss"
    assert classify_row(rows["cr-008"]) == "all_reject"
    assert classify_row(rows["cr-002"]) == "none"


def test_bad_case_collector_writes_jsonl(tmp_path: Path) -> None:
    """Below-threshold samples become classified JSONL records."""
    report = tmp_path / "r.md"
    report.write_text(_REPORT, encoding="utf-8")
    fixtures = _write_fixtures(tmp_path)
    collector = BadCaseCollector(fixtures)

    records = collector.collect(report, threshold=0.7)

    assert [r.sample_id for r in records] == ["cr-001", "cr-008"]
    assert records[0].failure_type == "miss"
    assert records[1].failure_type == "all_reject"
    target = collector.write(records, tmp_path / "bad")
    lines = target.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    payload = json.loads(lines[0])
    assert payload["sample_id"] == "cr-001"
    assert payload["candidates_digest"]["false_negatives"] == [
        "cr-001-a2",
        "cr-001-a3",
    ]


def _row(index: int, source: str) -> SourceRow:
    return SourceRow(
        id=f"row-{index}",
        title=f"Title {index}",
        description="A sufficiently long description of an AI release.",
        url=f"https://example.test/{index}",
        source=source,
        category="ai",
    )


def test_build_pools_balances_sources() -> None:
    """Round-robin pools cap per-source contribution and never overlap ids."""
    sources = [f"src-{i}" for i in range(12)]
    rows = [_row(index, sources[index % len(sources)]) for index in range(60)]
    pools = build_pools(rows, count=5, balanced_per_source=1)
    assert len(pools) == 5
    for pool in pools:
        assert len(pool) == 10
        seen: set[str] = set()
        for row in pool:
            assert row["id"] not in seen
            seen.add(row["id"])


def test_trace_sink_writes_gzip_and_prunes(tmp_path: Path) -> None:
    """Traces persist as jsonl.gz and archives older than retain_days are pruned."""
    sink = TraceSink(tmp_path / "traces", retain_days=7)
    target = sink.write([SampleTrace(sample_id="cr-001", steps_planned=["curate"])])
    with gzip.open(target, "rt", encoding="utf-8") as handle:
        payload = json.loads(handle.read().strip())
    assert payload["sample_id"] == "cr-001"

    stale = tmp_path / "traces" / "benchmark_20200101-000000.jsonl.gz"
    stale.write_bytes(b"{}")
    past = datetime.now(UTC).timestamp() - 8 * 24 * 3600
    import os

    os.utime(stale, (past, past))
    removed = sink.prune(now=datetime.now(UTC))
    assert removed == 1
    assert not stale.exists()
    assert target.exists()
