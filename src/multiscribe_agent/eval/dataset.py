"""YAML-based evaluation datasets with strict schema validation."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, ValidationError


class DatasetSample(BaseModel):
    """One replayable pipeline-state sample."""

    id: str = Field(min_length=1)
    input_path: str
    expected_tags: list[str] = Field(default_factory=list)
    expected_min_score: float = Field(default=0.7, ge=0.0, le=1.0)
    notes: str = ""


class Dataset(BaseModel):
    """A named collection of pipeline-state samples and a rubric."""

    name: str = Field(min_length=1)
    description: str
    samples: list[DatasetSample] = Field(min_length=1)
    rubric: Literal["tech-weekly", "summary-quality"] = "tech-weekly"


def load_dataset(path: Path) -> Dataset:
    """Load and validate a UTF-8 YAML dataset file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return Dataset.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ValueError(f"Invalid dataset {path}: {exc}") from exc
