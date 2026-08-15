"""Create validated label-update fixture drafts from bad cases and LLM proposals.

Safe default: dry-run prints a unified diff and makes no filesystem changes.
Only ``--apply`` writes a draft under an explicit draft directory; protected
``tests/eval/fixtures`` files are never changed by this command.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from multiscribe_agent.eval.cleaner.fixture_draft import (
    bad_case_ids,
    build_fixture_draft,
    unified_fixture_diff,
)


def fixture_path(fixtures_dir: Path, sample_id: str) -> Path:
    """Resolve the conventional cr-NNN fixture filename for a sample id."""
    return fixtures_dir / f"{sample_id.replace('-', '_')}.json"


def main() -> None:
    """Validate a proposal and preview or write one reviewable fixture draft."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--bad-cases", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--fixtures-dir", type=Path, default=Path("tests/eval/fixtures"))
    parser.add_argument("--draft-dir", type=Path, default=Path("data/eval/fixture_drafts"))
    parser.add_argument("--labeled-by", default="zcode:P64.3-draft")
    parser.add_argument("--apply", action="store_true", help="write a draft after validation")
    args = parser.parse_args()

    represented = bad_case_ids(args.bad_cases)
    if args.sample_id not in represented:
        parser.error(f"{args.sample_id} is not present in {args.bad_cases}")
    original_path = fixture_path(args.fixtures_dir, args.sample_id)
    if not original_path.exists():
        parser.error(f"fixture not found: {original_path}")
    original: dict[str, object] = json.loads(original_path.read_text(encoding="utf-8"))
    proposal: dict[str, object] = json.loads(args.proposal.read_text(encoding="utf-8"))
    draft = build_fixture_draft(
        args.sample_id, original, proposal, labeled_by=args.labeled_by
    )
    diff = unified_fixture_diff(original, draft, original_path)

    if not args.apply:
        print(diff or "No label changes proposed.")
        print("DRY-RUN: no files written")
        return

    args.draft_dir.mkdir(parents=True, exist_ok=True)
    target = fixture_path(args.draft_dir, args.sample_id)
    target.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(diff or "No label changes proposed.")
    print(f"WROTE DRAFT: {target}")


if __name__ == "__main__":
    main()
