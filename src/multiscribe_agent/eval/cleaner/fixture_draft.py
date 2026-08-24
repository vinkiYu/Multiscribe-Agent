"""Build reviewable label-update drafts without mutating protected fixtures."""

from __future__ import annotations

import difflib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from multiscribe_agent.eval.cleaner.label_normalizer import LabelNormalizer
from multiscribe_agent.eval.cleaner.schema_validator import FixturePayload, SchemaValidator


def bad_case_ids(path: Path) -> set[str]:
    """Read the sample IDs represented in one BadCaseCollector JSONL file."""
    ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid bad-case JSONL {path}:{line_number}: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("sample_id"), str):
            raise ValueError(f"Invalid bad-case JSONL {path}:{line_number}: missing sample_id")
        ids.add(payload["sample_id"])
    return ids


def build_fixture_draft(
    sample_id: str,
    fixture: dict[str, object],
    proposal: dict[str, object],
    *,
    labeled_by: str,
) -> dict[str, object]:
    """Apply one normalized proposal to a complete fixture in memory and validate it."""
    proposal_id = proposal.get("sample_id", sample_id)
    if proposal_id != sample_id:
        raise ValueError(f"proposal sample_id {proposal_id!r} does not match fixture {sample_id!r}")
    normalized = LabelNormalizer().normalize({sample_id: proposal})[sample_id]
    candidates = fixture.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError(f"fixture {sample_id!r} has no candidates")
    candidate_ids = {
        candidate["id"]
        for candidate in candidates
        if isinstance(candidate, dict) and isinstance(candidate.get("id"), str)
    }
    selected = normalized["selected_ids"]
    unknown = sorted(set(selected) - candidate_ids)
    if unknown:
        raise ValueError(
            f"{sample_id}: proposal selects unknown candidate IDs: {', '.join(unknown)}"
        )
    schema_version = fixture.get("schema_version", 1)
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ValueError(f"fixture {sample_id!r} schema_version must be an integer")
    draft = dict(fixture)
    draft["id"] = sample_id
    draft["expected_selected_ids"] = selected
    draft["expected_rejected_ids"] = sorted(candidate_ids - set(selected))
    draft["selection_rationale"] = normalized["rationale"]
    draft["schema_version"] = schema_version + 1
    draft["labeled_by"] = labeled_by
    draft["labeled_at"] = datetime.now(UTC).date().isoformat()
    SchemaValidator().validate(cast("FixturePayload", draft))
    return draft


def unified_fixture_diff(original: dict[str, object], draft: dict[str, object], path: Path) -> str:
    """Render a JSON unified diff suitable for human review in dry-run mode."""
    before = json.dumps(original, ensure_ascii=False, indent=2, sort_keys=True).splitlines(
        keepends=True
    )
    after = json.dumps(draft, ensure_ascii=False, indent=2, sort_keys=True).splitlines(
        keepends=True
    )
    return "".join(difflib.unified_diff(before, after, fromfile=str(path), tofile=f"{path}.draft"))


__all__ = ["bad_case_ids", "build_fixture_draft", "unified_fixture_diff"]
