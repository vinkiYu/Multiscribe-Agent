"""Tests for backend-neutral SQL placeholder helpers."""

from __future__ import annotations

import pytest

from multiscribe_agent.infra.db import SqliteDatabase
from multiscribe_agent.infra.db_protocol import PlaceholderStyle
from multiscribe_agent.infra.placeholder import (
    DOLLAR,
    PERCENT,
    QUESTION_MARK,
    PlaceholderGenerator,
    translate_question_marks,
)


def test_sqlite_database_declares_question_mark_placeholders() -> None:
    """SQLite advertises its native parameter dialect without changing behavior."""
    database = SqliteDatabase(connection=object())  # type: ignore[arg-type]

    assert database.placeholder_style is PlaceholderStyle.QUESTION_MARK


@pytest.mark.parametrize(
    ("generator", "count", "expected"),
    [
        (DOLLAR, 3, "$1, $2, $3"),
        (QUESTION_MARK, 3, "?, ?, ?"),
        (PERCENT, 1, "%s"),
    ],
)
def test_placeholder_generator_builds_dialect_specific_sequences(
    generator: PlaceholderGenerator, count: int, expected: str
) -> None:
    """Generators preserve dialect-specific parameter notation and order."""
    assert generator.for_count(count) == expected
    if count == 1:
        assert generator.for_one() == expected


@pytest.mark.parametrize("count", [-1])
def test_placeholder_generator_rejects_negative_counts(count: int) -> None:
    """A placeholder list cannot have a negative number of parameters."""
    with pytest.raises(ValueError, match="cannot be negative"):
        DOLLAR.for_count(count)


def test_placeholder_generator_rejects_unknown_style() -> None:
    """Unknown backends fail explicitly instead of generating invalid SQL."""
    generator = PlaceholderGenerator("unknown")

    with pytest.raises(ValueError, match="Unknown placeholder style"):
        generator.for_one()


@pytest.mark.parametrize(
    ("sql", "target", "expected"),
    [
        ("", "dollar", ""),
        ("SELECT ?", "dollar", "SELECT $1"),
        ("SELECT ? FROM items WHERE id = ?", "dollar", "SELECT $1 FROM items WHERE id = $2"),
        ("SELECT '?' AS literal, ?", "dollar", "SELECT '?' AS literal, $1"),
        ('SELECT "?" AS identifier, ?', "dollar", 'SELECT "?" AS identifier, $1'),
        ("SELECT 'it''s ?' AS literal, ?", "percent", "SELECT 'it''s ?' AS literal, %s"),
        ("SELECT ?", "question_mark", "SELECT ?"),
    ],
)
def test_translate_question_marks_respects_quoted_literals(
    sql: str, target: str, expected: str
) -> None:
    """Only real bind placeholders participate in translation."""
    assert translate_question_marks(sql, target) == expected


def test_translate_question_marks_rejects_invalid_input() -> None:
    """Unsupported targets and malformed literal boundaries fail explicitly."""
    with pytest.raises(ValueError, match="Unsupported target dialect"):
        translate_question_marks("SELECT ?", "colon")
    with pytest.raises(ValueError, match="unclosed quoted literal"):
        translate_question_marks("SELECT 'unfinished ?", "dollar")
