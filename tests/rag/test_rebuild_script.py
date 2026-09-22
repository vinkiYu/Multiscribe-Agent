"""Tests for resumable rebuild command bookkeeping."""

from __future__ import annotations

from scripts.rebuild_rag_index import _read_cursor, _write_cursor, build_parser


def test_rebuild_defaults_to_incremental_and_cursor_round_trip(tmp_path) -> None:
    """The command resumes from a persisted document_id without changing data."""
    args = build_parser().parse_args([])
    assert args.full is False
    assert args.resume is False

    cursor = tmp_path / "cursor.json"
    _write_cursor(cursor, "kb:document-2")
    assert _read_cursor(cursor) == "kb:document-2"


def test_malformed_cursor_starts_from_beginning(tmp_path) -> None:
    """A partial cursor cannot make a rebuild skip documents silently."""
    cursor = tmp_path / "cursor.json"
    cursor.write_text("not-json", encoding="utf-8")

    assert _read_cursor(cursor) == ""
