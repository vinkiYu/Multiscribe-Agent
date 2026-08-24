"""Normalize LLM-proposed label payloads into the fixture label schema."""

from __future__ import annotations

from typing import TypedDict


class NormalizedLabel(TypedDict):
    """One sample's normalized label payload."""

    selected_ids: list[str]
    rationale: str


class LabelNormalizer:
    """Accept messy LLM label JSON and emit the fixture label contract."""

    def normalize(self, raw: dict[str, object]) -> dict[str, NormalizedLabel]:
        """Normalize {sample_key: label} with key/id alias tolerance.

        Accepts sample keys written as ``cr_001`` or ``cr-001`` and selection
        fields named ``selected`` or ``selected_ids``.
        """
        normalized: dict[str, NormalizedLabel] = {}
        for key, value in raw.items():
            sample_id = str(key).replace("_", "-")
            if not isinstance(value, dict):
                raise ValueError(f"{sample_id}: label payload must be an object")
            selected = value.get("selected_ids", value.get("selected"))
            if not isinstance(selected, list) or not all(
                isinstance(item, str) for item in selected
            ):
                raise ValueError(f"{sample_id}: selected_ids must be a list of strings")
            rationale = value.get("rationale", "")
            if not isinstance(rationale, str):
                raise ValueError(f"{sample_id}: rationale must be a string")
            normalized[sample_id] = NormalizedLabel(
                selected_ids=sorted(set(selected)), rationale=rationale
            )
        return normalized


__all__ = ["LabelNormalizer", "NormalizedLabel"]
