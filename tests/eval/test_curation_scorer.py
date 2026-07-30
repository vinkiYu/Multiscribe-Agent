"""Tests for curation precision, recall, and F1 calculations."""

from __future__ import annotations

from multiscribe_agent.eval.curation_scorer import score_curation


def test_precision() -> None:
    """Precision counts false positives among selected IDs."""
    score = score_curation({"a", "b"}, {"a"})

    assert score.precision == 0.5


def test_recall() -> None:
    """Recall counts expected IDs that were actually selected."""
    score = score_curation({"a"}, {"a", "b"})

    assert score.recall == 0.5


def test_f1_perfect_match() -> None:
    """A complete match has a perfect harmonic mean."""
    score = score_curation({"a", "b"}, {"a", "b"})

    assert score.precision == 1.0
    assert score.recall == 1.0
    assert score.f1 == 1.0
    assert score.passed


def test_empty_selection_and_expected_boundaries() -> None:
    """Empty selections score zero precision while an empty target has full recall."""
    empty_selection = score_curation(set(), {"a"})
    empty_expected = score_curation({"a"}, set())

    assert empty_selection.precision == 0.0
    assert empty_selection.recall == 0.0
    assert empty_expected.precision == 0.0
    assert empty_expected.recall == 1.0
