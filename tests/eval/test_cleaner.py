"""Tests for the P64.2 cleaner package."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from multiscribe_agent.eval.cleaner.dedup_hasher import DedupHasher
from multiscribe_agent.eval.cleaner.label_auditor import LabelAuditor
from multiscribe_agent.eval.cleaner.label_normalizer import LabelNormalizer
from multiscribe_agent.eval.cleaner.schema_validator import SchemaValidator
from multiscribe_agent.eval.curation_dataset import CurationSample


def test_label_normalizer_accepts_aliases() -> None:
    """cr_001 / cr-001 keys and selected / selected_ids both normalize."""
    normalizer = LabelNormalizer()
    normalized = normalizer.normalize(
        {
            "cr_001": {"selected": ["b", "a", "a"], "rationale": "ok"},
            "cr-002": {"selected_ids": ["x"], "rationale": ""},
        }
    )
    assert normalized["cr-001"]["selected_ids"] == ["a", "b"]
    assert normalized["cr-002"]["selected_ids"] == ["x"]


def test_label_normalizer_rejects_bad_payloads() -> None:
    """Non-list selections and non-dict payloads raise ValueError."""
    normalizer = LabelNormalizer()
    with pytest.raises(ValueError, match="must be an object"):
        normalizer.normalize({"cr-001": ["a"]})
    with pytest.raises(ValueError, match="list of strings"):
        normalizer.normalize({"cr-001": {"selected": [1, 2]}})


def _payload() -> dict[str, object]:
    return {
        "id": "cr-001",
        "candidates": [
            {
                "id": "cr-001-a1",
                "title": "t1",
                "description": "d1",
                "url": "https://example.test/1",
                "source": "rss",
            },
            {
                "id": "cr-001-a2",
                "title": "t2",
                "description": "d2",
                "url": "https://example.test/2",
                "source": "rss",
            },
        ],
        "expected_selected_ids": ["cr-001-a1"],
        "expected_rejected_ids": ["cr-001-a2"],
        "selection_rationale": "test",
    }


def test_schema_validator_accepts_valid_fixture() -> None:
    sample = SchemaValidator().validate(_payload())  # type: ignore[arg-type]
    assert isinstance(sample, CurationSample)
    assert sample.id == "cr-001"


def test_schema_validator_rejects_contradictory_labels() -> None:
    payload = _payload()
    payload["expected_rejected_ids"] = ["cr-001-a1", "cr-001-a2"]
    with pytest.raises(ValueError, match="labels overlap"):
        SchemaValidator().validate(payload)  # type: ignore[arg-type]


def test_dedup_hasher_finds_cross_source_duplicates() -> None:
    """Same normalized title across samples/sources groups into one duplicate."""
    hasher = DedupHasher()
    fixtures = {
        "cr-001": [
            {"id": "a", "title": "GPT-5.4 Released!", "url": "https://one.test/x", "source": "rss"},
            {"id": "b", "title": "Unrelated item", "url": "https://one.test/y", "source": "rss"},
        ],
        "cr-002": [
            {
                "id": "c",
                "title": "gpt 5 4 released",
                "url": "https://two.test/z",
                "source": "other",
            },
        ],
    }
    groups = hasher.find_duplicates(fixtures)
    assert len(groups) == 1
    members = groups[0].members
    assert {m.candidate_id for m in members} == {"a", "c"}
    assert {m.source for m in members} == {"rss", "other"}


def test_dedup_hasher_no_duplicates() -> None:
    hasher = DedupHasher()
    fixtures = {
        "cr-001": [
            {"id": "a", "title": "Alpha release", "url": "https://one.test/a", "source": "rss"},
        ],
        "cr-002": [
            {"id": "b", "title": "Beta launch", "url": "https://one.test/b", "source": "rss"},
        ],
    }
    assert hasher.find_duplicates(fixtures) == []


class _FirstCandidateProvider:
    """Always select the first candidate embedded in the curation prompt."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, messages: list[object], **_: object) -> object:
        import re

        from multiscribe_agent.domain.models import AIResponse

        self.calls += 1
        prompt = str(messages[0].content)
        match = re.search(r'"id":\s*"(cr-\d+-a\d+)"', prompt)
        selected = match.group(1) if match else ""
        content = json.dumps([{"id": selected}] if selected else [])
        return AIResponse(content=content)


@pytest.mark.asyncio
async def test_label_auditor_records_dispute_on_disagreement() -> None:
    """Expecting two candidates while the auditor picks one yields one dispute."""
    sample = CurationSample(
        id="cr-001",
        candidates=[
            {
                "id": "cr-001-a1",
                "title": "t1",
                "description": "d1",
                "url": "https://example.test/1",
                "source": "rss",
            },
            {
                "id": "cr-001-a2",
                "title": "t2",
                "description": "d2",
                "url": "https://example.test/2",
                "source": "rss",
            },
        ],
        expected_selected_ids=["cr-001-a1", "cr-001-a2"],
        expected_rejected_ids=[],
    )
    auditor = LabelAuditor(provider=_FirstCandidateProvider(), seed=64)

    disputes = await auditor.audit([sample], ratio=1.0)

    assert len(disputes) == 1
    assert disputes[0].missing_from_auditor == ["cr-001-a2"]
    assert disputes[0].extra_from_auditor == []


def test_label_auditor_pick_samples_deterministic() -> None:
    """Sampling is seeded, capped at the population, and ordered by id."""
    samples = [
        CurationSample(
            id=f"cr-{i:03d}",
            candidates=[
                {
                    "id": f"cr-{i:03d}-a1",
                    "title": f"t{i}",
                    "description": "d",
                    "url": f"https://example.test/{i}",
                    "source": "rss",
                }
            ],
            expected_selected_ids=[f"cr-{i:03d}-a1"],
            expected_rejected_ids=[],
        )
        for i in range(1, 21)
    ]
    auditor = LabelAuditor(provider=None, seed=64)  # type: ignore[arg-type]
    picked = auditor.pick_samples(samples, ratio=0.1)
    assert len(picked) == 2
    assert picked == auditor.pick_samples(samples, ratio=0.1)


def test_label_auditor_write_empty_disputes(tmp_path: Path) -> None:
    """An empty dispute list still writes a valid (empty) JSON file."""
    auditor = LabelAuditor(provider=None)  # type: ignore[arg-type]
    target = auditor.write([], tmp_path)
    assert json.loads(target.read_text(encoding="utf-8")) == []
