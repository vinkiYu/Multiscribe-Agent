"""Five-class failure classification shared by collectors and analyzers (P64.2 T10).

Plan predicates (docs/phases/P64.2 五段链路.md §T10):
- all_reject  : the model selected nothing (recall = 0)
- miss        : FN >= 2 and FP = 0
- over_select : FP >= 2 and FN = 0
- mixed       : FP >= 1 and FN >= 1
- boundary    : exactly one FP (keyword hit recorded separately)

The plan predicates leave two shapes uncovered (FP==1/FN==0 without a boundary
keyword, and FN==1/FP==0). Both are folded into the closest class instead of
inventing a sixth: single FP -> boundary (keyword recorded), single FN -> miss.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

# Boundary cues mirror the rejection rationale patterns seen in P57 labeling
# (教程/Academy, 企业稿, 营销, 非 AI 工具, "拒以稳妥" borderline items).
BOUNDARY_KEYWORDS: tuple[str, ...] = (
    "tutorial",
    "course",
    "academy",
    "教程",
    "课程",
    "企业稿",
    "营销",
    "marketing",
    "案例",
    "case study",
    "非 ai",
    "工具",
    "边界",
    "拒以稳妥",
)


@dataclass(frozen=True, slots=True)
class FailureClassification:
    """One sample's failure class plus the evidence used to derive it."""

    failure_type: str
    false_negatives: tuple[str, ...]
    false_positives: tuple[str, ...]
    boundary_keyword_hit: bool


def boundary_keyword_hit(texts: Iterable[str]) -> str | None:
    """Return the first matched boundary keyword across the given texts."""
    joined = " ".join(texts).casefold()
    for keyword in BOUNDARY_KEYWORDS:
        if keyword in joined:
            return keyword
    return None


def classify_failure(
    expected_ids: set[str], selected_ids: set[str]
) -> FailureClassification | None:
    """Classify one sample; ``None`` means the sample has no failure to explain."""
    missed = tuple(sorted(expected_ids - selected_ids))
    extra = tuple(sorted(selected_ids - expected_ids))
    fn, fp = len(missed), len(extra)
    if fn == 0 and fp == 0:
        return None
    if not selected_ids:
        failure_type = "all_reject"
    elif fn >= 1 and fp >= 1:
        failure_type = "mixed"
    elif fn >= 2 and fp == 0:
        failure_type = "miss"
    elif fp >= 2 and fn == 0:
        failure_type = "over_select"
    elif fp == 1 and fn == 0:
        failure_type = "boundary"
    else:  # fn == 1 and fp == 0: single miss folds into the closest class.
        failure_type = "miss"
    keyword = boundary_keyword_hit(missed + extra)
    return FailureClassification(
        failure_type=failure_type,
        false_negatives=missed,
        false_positives=extra,
        boundary_keyword_hit=keyword is not None,
    )


__all__ = ["BOUNDARY_KEYWORDS", "FailureClassification", "boundary_keyword_hit", "classify_failure"]
