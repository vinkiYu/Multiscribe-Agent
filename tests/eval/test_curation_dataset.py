"""Tests for ground-truth curation candidate-pool datasets."""

from __future__ import annotations

from pathlib import Path

import pytest

from multiscribe_agent.eval.curation_dataset import load_curation_dataset


def test_load_curation_dataset() -> None:
    """The shipped YAML resolves all 50 JSON candidate fixtures with labels."""
    dataset = load_curation_dataset(Path("data/eval/datasets/curation_recall.yaml"))

    assert dataset.name == "curation-recall"
    assert len(dataset.samples) == 50
    assert len(dataset.samples[0].candidates) == 10
    assert dataset.samples[0].candidates[0].title.startswith("Pushing")
    for sample in dataset.samples:
        assert sample.expected_selected_ids, f"sample {sample.id} has no labels"
        assert sample.expected_rejected_ids, f"sample {sample.id} has no labels"
        assert set(sample.expected_selected_ids).isdisjoint(
            sample.expected_rejected_ids
        ), f"sample {sample.id} labels overlap"
        candidate_ids = {candidate.id for candidate in sample.candidates}
        labeled = set(sample.expected_selected_ids) | set(sample.expected_rejected_ids)
        assert labeled == candidate_ids, (
            f"sample {sample.id} labels do not cover all candidates: "
            f"missing={candidate_ids - labeled} extra={labeled - candidate_ids}"
        )


def test_overlapping_labels_rejected(tmp_path: Path) -> None:
    """A candidate cannot be both expected selected and expected rejected."""
    dataset_path = tmp_path / "invalid.yaml"
    dataset_path.write_text(
        """name: invalid
description: invalid labels
samples:
  - id: sample
    candidates:
      - id: one
        title: One
        description: Description
        url: https://example.test/one
        source: rss
    expected_selected_ids: [one]
    expected_rejected_ids: [one]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="labels overlap"):
        load_curation_dataset(dataset_path)


def test_fixture_label_validation_rejects_unknown_id(tmp_path: Path) -> None:
    """Labels must refer to candidates in the same pool."""
    dataset_path = tmp_path / "invalid.yaml"
    dataset_path.write_text(
        """name: invalid
description: invalid labels
samples:
  - id: sample
    candidates:
      - id: one
        title: One
        description: Description
        url: https://example.test/one
        source: rss
    expected_selected_ids: [missing]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown candidates"):
        load_curation_dataset(dataset_path)
