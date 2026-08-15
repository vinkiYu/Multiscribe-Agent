"""Tests for reviewable fixture label-update drafts (P64.3 T15)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from multiscribe_agent.eval.cleaner.fixture_draft import (
    bad_case_ids,
    build_fixture_draft,
    unified_fixture_diff,
)


def _fixture() -> dict[str, object]:
    return {
        "candidates": [
            {
                "id": "cr-001-a1",
                "title": "Model release",
                "description": "A substantive model update.",
                "url": "https://example.test/a1",
                "source": "rss",
            },
            {
                "id": "cr-001-a2",
                "title": "Tool release",
                "description": "A substantive agent tool update.",
                "url": "https://example.test/a2",
                "source": "rss",
            },
        ],
        "expected_selected_ids": ["cr-001-a1"],
        "expected_rejected_ids": ["cr-001-a2"],
        "selection_rationale": "old",
        "schema_version": 1,
    }


def _proposal(selected_ids: list[str]) -> dict[str, object]:
    return {
        "sample_id": "cr-001",
        "selected_ids": selected_ids,
        "rationale": "new rationale",
    }


def test_build_draft_preserves_complete_candidates_and_validates() -> None:
    original = _fixture()
    draft = build_fixture_draft("cr-001", original, _proposal(["cr-001-a2"]), labeled_by="test")

    assert draft["candidates"] == original["candidates"]
    assert draft["expected_selected_ids"] == ["cr-001-a2"]
    assert draft["expected_rejected_ids"] == ["cr-001-a1"]
    assert draft["selection_rationale"] == "new rationale"
    assert draft["schema_version"] == 2
    assert "expected_selected_ids" in unified_fixture_diff(original, draft, Path("fixture.json"))


def test_unknown_candidate_rejects_before_any_write() -> None:
    with pytest.raises(ValueError, match="unknown candidate"):
        build_fixture_draft("cr-001", _fixture(), _proposal(["missing"]), labeled_by="test")


def test_bad_case_ids_reads_jsonl_and_rejects_bad_rows(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"sample_id":"cr-001"}\n', encoding="utf-8")
    assert bad_case_ids(path) == {"cr-001"}

    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing sample_id"):
        bad_case_ids(path)


def test_dry_run_input_does_not_need_a_draft_directory(tmp_path: Path) -> None:
    """Pure builder/diff path leaves a caller-owned draft location untouched."""
    draft_dir = tmp_path / "drafts"
    original = _fixture()
    draft = build_fixture_draft("cr-001", original, _proposal(["cr-001-a2"]), labeled_by="test")
    _ = unified_fixture_diff(original, draft, tmp_path / "cr_001.json")
    assert not draft_dir.exists()


def test_draft_is_json_serializable() -> None:
    draft = build_fixture_draft("cr-001", _fixture(), _proposal(["cr-001-a1"]), labeled_by="test")
    assert json.loads(json.dumps(draft, ensure_ascii=False))["id"] == "cr-001"
