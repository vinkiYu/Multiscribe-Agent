"""Bad-case collector: mine failed samples from a benchmark report into JSONL."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from multiscribe_agent.eval.failure_types import classify_failure

# Rows look like:
# "| cr-001 | 0.250 | 1.000 | 0.400 | 失败 | sel=cr-001-a4;exp=cr-001-a1,cr-001-a4 |"
_ROW_RE = re.compile(
    r"^\|\s*(?P<sample_id>cr-\d+)\s*\|"
    r"\s*(?P<precision>[\d.]+)\s*\|\s*(?P<recall>[\d.]+)\s*\|\s*(?P<f1>[\d.]+)\s*\|"
    r"[^|]*\|\s*(?P<selection>[^|]*)"
)
_SELECTION_RE = re.compile(r"sel=(?P<sel>[^;]*);exp=(?P<exp>.*)")


@dataclass(frozen=True, slots=True)
class ReportRow:
    """One parsed report-table row."""

    sample_id: str
    precision: float
    recall: float
    f1: float
    selected_ids: frozenset[str]
    expected_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class BadCaseRecord:
    """One failed sample serialized into data/eval/bad_cases/*.jsonl."""

    sample_id: str
    f1: float
    precision: float
    recall: float
    failure_type: str
    candidates_digest: dict[str, object]
    collected_at: str


def parse_report_rows(report_path: Path) -> dict[str, ReportRow]:
    """Parse the per-sample table; selection sets fall back to empty when absent."""
    rows: dict[str, ReportRow] = {}
    for line in report_path.read_text(encoding="utf-8").splitlines():
        match = _ROW_RE.match(line.strip())
        if match is None:
            continue
        selection = _SELECTION_RE.search(match["selection"])
        if selection is None:
            selected: frozenset[str] = frozenset()
            expected: frozenset[str] = frozenset()
        else:
            selected = frozenset(
                item for item in selection["sel"].strip().split(",") if item
            )
            expected = frozenset(
                item for item in selection["exp"].strip().split(",") if item
            )
        rows[match["sample_id"]] = ReportRow(
            sample_id=match["sample_id"],
            precision=float(match["precision"]),
            recall=float(match["recall"]),
            f1=float(match["f1"]),
            selected_ids=selected,
            expected_ids=expected,
        )
    return rows


def derive_counts(precision: float, recall: float, expected_count: int) -> tuple[int, int]:
    """Derive (FN, FP) from aggregate scores when exact sets are unavailable."""
    true_positives = recall * expected_count
    false_negatives = expected_count - true_positives
    if precision <= 0.0:
        false_positives = 2.0 if true_positives > 0 else float(expected_count)
    else:
        false_positives = true_positives * (1.0 - precision) / precision
    return round(false_negatives), round(false_positives)


def classify_row(row: ReportRow) -> str:
    """Classify one row: exact diff sets when present, derived counts otherwise."""
    if row.selected_ids or row.expected_ids:
        classification = classify_failure(set(row.expected_ids), set(row.selected_ids))
        return classification.failure_type if classification else "none"
    false_negatives, false_positives = derive_counts(
        row.precision, row.recall, len(row.expected_ids)
    )
    if row.recall <= 0.0 and false_positives == 0:
        return "all_reject"
    if false_negatives >= 1 and false_positives >= 1:
        return "mixed"
    if false_negatives >= 2 and false_positives == 0:
        return "miss"
    if false_positives >= 2 and false_negatives == 0:
        return "over_select"
    if false_positives == 1 and false_negatives == 0:
        return "boundary"
    return "miss"


class BadCaseCollector:
    """Collect failed samples below an F1 threshold into dated JSONL files."""

    def __init__(self, fixtures_dir: Path) -> None:
        self.fixtures_dir = fixtures_dir

    def collect(self, report_path: Path, threshold: float = 0.7) -> list[BadCaseRecord]:
        """Classify every below-threshold sample using its fixture context."""
        rows = parse_report_rows(report_path)
        records: list[BadCaseRecord] = []
        collected_at = datetime.now(UTC).isoformat(timespec="seconds")
        for sample_id, row in sorted(rows.items()):
            if row.f1 >= threshold:
                continue
            fixture = self._load_fixture(sample_id)
            if fixture is None:
                continue
            candidates = cast("list[dict[str, str]]", fixture.get("candidates", []))
            classification = classify_failure(
                set(row.expected_ids), set(row.selected_ids)
            )
            failure_type = (
                classification.failure_type if classification else classify_row(row)
            )
            digest = {
                "selected_ids": sorted(row.selected_ids),
                "expected_ids": sorted(row.expected_ids),
                "false_negatives": list(classification.false_negatives) if classification else [],
                "false_positives": list(classification.false_positives) if classification else [],
                "candidates": [
                    {"id": c["id"], "title": c["title"], "source": c["source"]}
                    for c in candidates
                ],
            }
            records.append(
                BadCaseRecord(
                    sample_id=sample_id,
                    f1=row.f1,
                    precision=row.precision,
                    recall=row.recall,
                    failure_type=failure_type,
                    candidates_digest=digest,
                    collected_at=collected_at,
                )
            )
        return records

    def write(self, records: list[BadCaseRecord], out_dir: Path) -> Path:
        """Write records to data/eval/bad_cases/YYYY-MM-DD.jsonl."""
        out_dir.mkdir(parents=True, exist_ok=True)
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        target = out_dir / f"{day}.jsonl"
        payload = "\n".join(json.dumps(asdict(r), ensure_ascii=False) for r in records)
        target.write_text(payload + "\n", encoding="utf-8")
        return target

    def _load_fixture(self, sample_id: str) -> dict[str, object] | None:
        path = self.fixtures_dir / f"{sample_id.replace('-', '_')}.json"
        if not path.exists():
            return None
        loaded: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
        return loaded


__all__ = [
    "BadCaseCollector",
    "BadCaseRecord",
    "ReportRow",
    "classify_row",
    "derive_counts",
    "parse_report_rows",
]
