"""Ground-truth precision, recall, and F1 scoring for curator selections."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CurationScore:
    """One curation selection score and the IDs used to calculate it."""

    precision: float
    recall: float
    f1: float
    selected_ids: frozenset[str]
    expected_selected_ids: frozenset[str]
    passed: bool


def score_curation(
    selected_ids: set[str], expected_selected_ids: set[str], threshold: float = 0.7
) -> CurationScore:
    """Calculate precision, recall, and F1 for one curator output."""
    selected = frozenset(selected_ids)
    expected = frozenset(expected_selected_ids)
    true_positives = len(selected & expected)
    precision = true_positives / len(selected) if selected else 0.0
    recall = true_positives / len(expected) if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return CurationScore(
        precision=precision,
        recall=recall,
        f1=f1,
        selected_ids=selected,
        expected_selected_ids=expected,
        passed=f1 >= threshold,
    )


__all__ = ["CurationScore", "score_curation"]
