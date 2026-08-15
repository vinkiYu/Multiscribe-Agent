"""Second-LLM label auditing with dispute export (P64.2 T8).

Re-runs curation with an independent judge pass over a sampled subset of
fixtures; any sample whose selection disagrees with the fixture labels becomes
a dispute record under ``data/eval/label_disputes/``.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from multiscribe_agent.eval.curation_benchmark import run_curation
from multiscribe_agent.eval.curation_dataset import CurationSample
from multiscribe_agent.llm.provider import AIProvider


@dataclass(frozen=True, slots=True)
class DisputeRecord:
    """One sample where the auditor disagreed with the fixture labels."""

    sample_id: str
    fixture_selected: list[str]
    auditor_selected: list[str]
    missing_from_auditor: list[str]
    extra_from_auditor: list[str]
    audited_at: str


class LabelAuditor:
    """Sample fixtures at a ratio and re-review them with a second LLM."""

    def __init__(self, provider: AIProvider, seed: int = 64) -> None:
        self.provider = provider
        self.seed = seed

    def pick_samples(
        self, samples: list[CurationSample], ratio: float = 0.1
    ) -> list[CurationSample]:
        """Deterministically sample ``max(1, round(len*ratio))`` fixtures."""
        if not 0.0 < ratio <= 1.0:
            raise ValueError("ratio must be in (0, 1]")
        count = max(1, round(len(samples) * ratio))
        rng = random.Random(self.seed)  # noqa: S311 - label sampling, not crypto
        picked = rng.sample(samples, min(count, len(samples)))
        return sorted(picked, key=lambda s: s.id)

    async def audit(self, samples: list[CurationSample], ratio: float = 0.1) -> list[DisputeRecord]:
        """Re-curate each sampled fixture and record disagreements."""
        disputes: list[DisputeRecord] = []
        audited_at = datetime.now(UTC).isoformat(timespec="seconds")
        for sample in self.pick_samples(samples, ratio):
            selected = await run_curation(
                self.provider, sample, max(len(sample.expected_selected_ids), 1)
            )
            expected = set(sample.expected_selected_ids)
            if selected == expected:
                continue
            disputes.append(
                DisputeRecord(
                    sample_id=sample.id,
                    fixture_selected=sorted(expected),
                    auditor_selected=sorted(selected),
                    missing_from_auditor=sorted(expected - selected),
                    extra_from_auditor=sorted(selected - expected),
                    audited_at=audited_at,
                )
            )
        return disputes

    def write(self, disputes: list[DisputeRecord], out_dir: Path) -> Path:
        """Persist disputes to data/eval/label_disputes/YYYY-MM-DD.json (may be empty)."""
        out_dir.mkdir(parents=True, exist_ok=True)
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        target = out_dir / f"{day}.json"
        target.write_text(
            json.dumps([asdict(d) for d in disputes], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target


__all__ = ["DisputeRecord", "LabelAuditor"]
