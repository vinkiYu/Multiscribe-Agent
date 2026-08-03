"""Guard the Eval-to-pipeline candidate projection contract against drift."""

from __future__ import annotations

from multiscribe_agent.agents.pipelines.daily_digest import (
    CURATE_SUMMARY_CHAR_LIMIT,
    _curate_item_dict,
)
from multiscribe_agent.domain.models import UnifiedData
from multiscribe_agent.eval.curation_benchmark import _project_candidate
from multiscribe_agent.eval.curation_dataset import CurationCandidate


def test_projection_fields_align_between_eval_and_pipeline() -> None:
    """Eval and pipeline must project the same fields and summary truncation."""
    long_description = "x" * 500
    item = UnifiedData(
        id="c1",
        title="Title",
        description=long_description,
        url="https://example.test/c1",
        published_date="2026-07-30",
        source="rss",
        category="tech",
    )
    candidate = CurationCandidate(
        id="c1",
        title="Title",
        description=long_description,
        url="https://example.test/c1",
        source="rss",
    )

    pipeline_view = _curate_item_dict(item)
    eval_view = _project_candidate(candidate)

    assert pipeline_view == eval_view
    assert len(str(pipeline_view["summary"])) == CURATE_SUMMARY_CHAR_LIMIT


def test_projection_github_trending_marker_aligns() -> None:
    """The github_trending to g=True marker must match across both projectors."""
    item = UnifiedData(
        id="g1",
        title="Trending",
        description="description",
        url="https://github.com/example/repo",
        published_date="2026-07-30",
        source="github_trending",
        category="tech",
    )
    candidate = CurationCandidate(
        id="g1",
        title="Trending",
        description="description",
        url="https://github.com/example/repo",
        source="github_trending",
    )

    assert _curate_item_dict(item).get("g") is True
    assert _project_candidate(candidate).get("g") is True
