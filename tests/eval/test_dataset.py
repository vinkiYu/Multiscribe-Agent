from pathlib import Path

import pytest

from multiscribe_agent.eval.dataset import load_dataset


def test_load_dataset_accepts_valid_yaml() -> None:
    dataset = load_dataset(Path("data/eval/datasets/tech_weekly.yaml"))
    assert dataset.name == "tech-weekly"
    assert len(dataset.samples) == 5


def test_load_dataset_rejects_missing_required_fields(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("name: broken\nsamples: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid dataset"):
        load_dataset(path)


def test_load_dataset_rejects_empty_samples(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("name: broken\ndescription: x\nsamples: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid dataset"):
        load_dataset(path)


def test_load_dataset_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid dataset"):
        load_dataset(tmp_path / "missing.yaml")
