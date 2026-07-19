from pathlib import Path

import pytest

from multiscribe_agent.eval.feedback_loop import load_refinement_workflow, trigger_refinement


def test_trigger_refinement_returns_none_when_score_passes() -> None:
    decision = trigger_refinement(8.0, dataset="tech-weekly", threshold=7.0)
    assert decision.action == "none"
    assert decision.suggested_workflow is None


def test_trigger_refinement_retries_near_threshold() -> None:
    decision = trigger_refinement(6.5, dataset="tech-weekly", threshold=7.0)
    assert decision.action == "retry"
    assert decision.suggested_workflow == "digest-retry"


def test_trigger_refinement_switches_when_alternate_workflow_exists(tmp_path: Path) -> None:
    (tmp_path / "alternate.yaml").write_text("id: alternate\n", encoding="utf-8")
    decision = trigger_refinement(3.0, threshold=7.0, workflows_dir=tmp_path)
    assert decision.action == "switch_agent"
    assert decision.suggested_workflow == "alternate"


def test_trigger_refinement_escalates_without_alternate() -> None:
    decision = trigger_refinement(3.0, threshold=7.0)
    assert decision.action == "human_review"


def test_load_refinement_workflow_reads_yaml(tmp_path: Path) -> None:
    (tmp_path / "digest-retry.yaml").write_text(
        "id: digest-retry\nname: Digest Retry\ndescription: Retry\nsteps: []\n",
        encoding="utf-8",
    )
    workflow = load_refinement_workflow("digest-retry", tmp_path)
    assert workflow.id == "digest-retry"


def test_load_refinement_workflow_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_refinement_workflow("missing", tmp_path)
