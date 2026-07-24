"""Verify curation projection fields, truncation, and realistic size ratios."""

from __future__ import annotations

import json

from multiscribe_agent.agents.pipelines.daily_digest import (
    _CURATE_SUMMARY_CHAR_LIMIT,
    _curate_item_dict,
)
from multiscribe_agent.domain.models import UnifiedData


def _make_item(description: str, index: int = 0) -> UnifiedData:
    """Build a representative normalized source item for projection tests."""
    return UnifiedData(
        id=f"item-{index}",
        title=f"标题{index}",
        url=f"https://example.com/{index}",
        description=description,
        published_date="2026-07-24",
        source="rss",
        category="tech",
        metadata={"tags": ["AI"], "score": index},
        author=f"author-{index}",
        status="active",
    )


def _projection_ratio(items: list[UnifiedData]) -> float:
    """Return projected JSON size divided by the former full-model JSON size."""
    full = json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False)
    projected = json.dumps([_curate_item_dict(item) for item in items], ensure_ascii=False)
    return len(projected) / len(full)


def test_projection_returns_only_id_title_summary() -> None:
    """The LLM projection excludes fields recovered after ID mapping."""
    projected = _curate_item_dict(_make_item("一段描述文字"))

    assert set(projected) == {"id", "title", "summary"}


def test_summary_is_truncated_to_limit() -> None:
    """Long descriptions are bounded to the configured 150-character excerpt."""
    projected = _curate_item_dict(_make_item("x" * 500))

    assert _CURATE_SUMMARY_CHAR_LIMIT == 150
    assert len(str(projected["summary"])) == 150


def test_short_summary_not_padded() -> None:
    """Short source descriptions remain unchanged."""
    projected = _curate_item_dict(_make_item("短描述"))

    assert projected["summary"] == "短描述"


def test_ratio_rss_short_descriptions() -> None:
    """One hundred typical short RSS summaries project below 30 percent."""
    description = "人工智能在医疗领域取得新突破, GPT-5 展现卓越诊断能力。"
    items = [_make_item(description, index) for index in range(100)]
    ratio = _projection_ratio(items)

    assert ratio < 0.30, f"RSS short-description projection ratio {ratio:.1%} exceeds 30%"


def test_ratio_mixed_realistic_distribution() -> None:
    """A deterministic 20/50/30 long, medium, and short mix stays below 30 percent."""
    long_description = "这是一篇关于人工智能发展历史的深度长文。" * 30
    medium_description = "<p>AI 技术持续发展, GPT-5 发布、Claude 升级。</p>"
    short_description = "AI在医疗领域取得新突破。"
    descriptions = [long_description] * 20 + [medium_description] * 50 + [short_description] * 30
    items = [_make_item(description, index) for index, description in enumerate(descriptions)]
    ratio = _projection_ratio(items)

    assert ratio < 0.30, f"Mixed-distribution projection ratio {ratio:.1%} exceeds 30%"
