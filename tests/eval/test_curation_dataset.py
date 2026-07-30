"""Tests for ground-truth curation candidate-pool datasets."""

from __future__ import annotations

from pathlib import Path

import pytest

from multiscribe_agent.eval.curation_dataset import load_curation_dataset


def test_load_curation_dataset() -> None:
    """The shipped YAML resolves all five JSON candidate fixtures."""
    dataset = load_curation_dataset(Path("data/eval/datasets/curation_recall.yaml"))

    assert dataset.name == "curation-recall"
    assert len(dataset.samples) == 5
    assert len(dataset.samples[0].candidates) == 10
    assert dataset.samples[0].candidates[0].title.startswith("OpenAI")
    assert set(dataset.samples[0].expected_selected_ids).isdisjoint(
        dataset.samples[0].expected_rejected_ids
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
