"""Gzipped trace sink with 7-day retention (P64.2 T7)."""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from multiscribe_agent.eval.trace_collector import SampleTrace


class TraceSink:
    """Persist per-sample step traces as JSONL gzip archives."""

    def __init__(self, out_dir: Path, retain_days: int = 7) -> None:
        self.out_dir = out_dir
        self.retain_days = retain_days

    def write(self, traces: list[SampleTrace]) -> Path:
        """Write one gzip archive per benchmark run and prune expired files."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        target = self.out_dir / f"benchmark_{timestamp}.jsonl.gz"
        payload = "\n".join(
            json.dumps(asdict(trace), ensure_ascii=False) for trace in traces
        )
        with gzip.open(target, "wt", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        self.prune()
        return target

    def prune(self, now: datetime | None = None) -> int:
        """Delete archives older than retain_days; return the removed count."""
        cutoff = (now or datetime.now(UTC)) - timedelta(days=self.retain_days)
        removed = 0
        for path in sorted(self.out_dir.glob("benchmark_*.jsonl.gz")):
            if datetime.fromtimestamp(path.stat().st_mtime, UTC) < cutoff:
                path.unlink()
                removed += 1
        return removed


__all__ = ["TraceSink"]
