"""Ground-truth candidate pools used by curation precision/recall benchmarks."""

from __future__ import annotations

import json
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, ValidationError, model_validator


class CurationCandidate(BaseModel):
    """Minimal source record projected into the curation prompt."""

    id: str = Field(min_length=1)
    title: str
    description: str
    url: str
    source: str


class CurationSample(BaseModel):
    """One annotated candidate pool and its expected selection labels."""

    id: str = Field(min_length=1)
    input_path: str | None = None
    candidates: list[CurationCandidate] = Field(default_factory=list, min_length=1)
    expected_selected_ids: list[str] = Field(default_factory=list)
    expected_rejected_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    selection_rationale: str = ""

    @model_validator(mode="after")
    def validate_labels(self) -> CurationSample:
        """Reject duplicate candidate IDs and contradictory labels."""
        candidate_ids = [candidate.id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError(f"sample {self.id!r} contains duplicate candidate IDs")
        selected = set(self.expected_selected_ids)
        rejected = set(self.expected_rejected_ids)
        overlap = selected & rejected
        if overlap:
            raise ValueError(f"sample {self.id!r} labels overlap: {', '.join(sorted(overlap))}")
        unknown = (selected | rejected) - set(candidate_ids)
        if unknown:
            raise ValueError(
                f"sample {self.id!r} labels unknown candidates: {', '.join(sorted(unknown))}"
            )
        return self


class CurationDataset(BaseModel):
    """A named collection of ground-truth curation samples."""

    name: str = Field(min_length=1)
    description: str
    samples: list[CurationSample] = Field(min_length=1)


def load_curation_dataset(path: Path) -> CurationDataset:
    """Load YAML metadata and referenced JSON candidate fixtures."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("dataset root must be an object")
        raw_samples = raw.get("samples")
        if not isinstance(raw_samples, list):
            raise ValueError("dataset samples must be a list")
        resolved_samples = [_resolve_sample(sample, path.parent) for sample in raw_samples]
        payload = dict(raw)
        payload["samples"] = resolved_samples
        return CurationDataset.model_validate(payload)
    except (OSError, json.JSONDecodeError, yaml.YAMLError, ValidationError, ValueError) as exc:
        raise ValueError(f"Invalid curation dataset {path}: {exc}") from exc


def _resolve_sample(raw_sample: object, dataset_dir: Path) -> dict[str, object]:
    """Merge one YAML sample with its optional JSON fixture payload."""
    if not isinstance(raw_sample, dict):
        raise ValueError("curation sample must be an object")
    sample: dict[str, object] = dict(raw_sample)
    input_path = sample.get("input_path")
    fixture: dict[str, object] = {}
    if isinstance(input_path, str) and input_path:
        fixture_path = dataset_dir / input_path
        if not fixture_path.is_file():
            fixture_path = Path.cwd() / input_path
        decoded = json.loads(fixture_path.read_text(encoding="utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError(f"fixture {fixture_path} must contain an object")
        fixture = decoded
    for key, value in fixture.items():
        sample.setdefault(key, value)
    if "id" not in sample:
        raise ValueError("curation sample is missing id")
    return sample


__all__ = [
    "CurationCandidate",
    "CurationDataset",
    "CurationSample",
    "load_curation_dataset",
]
