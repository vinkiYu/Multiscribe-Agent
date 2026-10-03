"""Tests for the PostgreSQL placeholder conversion helper."""

from __future__ import annotations

import pytest

from multiscribe_agent.infra.placeholder import (
    DOLLAR,
    PlaceholderGenerator,
    translate_question_marks,
)


def test_dollar_placeholder_generator_builds_numbered_sequence() -> None:
    """PostgreSQL binds are numbered and preserve parameter order."""
    assert DOLLAR.for_count(3) == "$1, $2, $3"
    assert DOLLAR.for_one() == "$1"


def test_placeholder_generator_rejects_negative_counts() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        DOLLAR.for_count(-1)


def test_placeholder_generator_rejects_unknown_style() -> None:
    with pytest.raises(ValueError, match="Unknown placeholder style"):
        PlaceholderGenerator("unknown").for_one()


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("", ""),
        ("SELECT ?", "SELECT $1"),
        ("SELECT ? FROM items WHERE id = ?", "SELECT $1 FROM items WHERE id = $2"),
        ("SELECT '?' AS literal, ?", "SELECT '?' AS literal, $1"),
        ('SELECT "?" AS identifier, ?', 'SELECT "?" AS identifier, $1'),
    ],
)
def test_translate_question_marks_respects_quoted_literals(sql: str, expected: str) -> None:
    """Only actual binds are translated to PostgreSQL numbered placeholders."""
    assert translate_question_marks(sql, "dollar") == expected


def test_translate_question_marks_rejects_invalid_input() -> None:
    with pytest.raises(ValueError, match="Unsupported target dialect"):
        translate_question_marks("SELECT ?", "colon")
    with pytest.raises(ValueError, match="unclosed quoted literal"):
        translate_question_marks("SELECT 'unfinished ?", "dollar")
