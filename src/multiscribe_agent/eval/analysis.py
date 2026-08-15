"""Failure analysis: five-class distribution, shared features, prompt advice (T10)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from multiscribe_agent.eval.collector.bad_case import (
    BadCaseCollector,
    BadCaseRecord,
)

_FAILURE_ORDER = ("all_reject", "miss", "over_select", "mixed", "boundary")

_PROMPT_ADVICE: dict[str, str] = {
    "all_reject": "模型整池拒选:检查 target_count 传递与 '宁可空选' 语气,考虑降低拒选倾向",
    "miss": "漏选集中在这些源/关键词:在 prompt 的入选标准中强化该类候选的正向描述",
    "over_select": "误选集中在这些源/关键词:在 prompt 的拒绝清单中显式加入该类模式",
    "mixed": "混合失败:先按漏选/误选各自的 Top 源分别处理,避免一次改两头",
    "boundary": "单条边界误选:把该候选的模式写进 '拒以稳妥' 示例,或修正 fixture 标签",
}


@dataclass(slots=True)
class FailureAnalysis:
    """Aggregated five-class view over one report's failed samples."""

    report: str
    total_failed: int
    distribution: dict[str, int] = field(default_factory=dict)
    samples_by_type: dict[str, list[str]] = field(default_factory=dict)
    source_stats_by_type: dict[str, Counter[str]] = field(default_factory=dict)
    keyword_stats_by_type: dict[str, Counter[str]] = field(default_factory=dict)


def analyze_failures(
    report_path: Path, fixtures_dir: Path, threshold: float = 0.7
) -> FailureAnalysis:
    """Classify failed samples and aggregate shared candidate features."""
    collector = BadCaseCollector(fixtures_dir)
    records = collector.collect(report_path, threshold)
    analysis = FailureAnalysis(
        report=str(report_path),
        total_failed=len(records),
        distribution=dict.fromkeys(_FAILURE_ORDER, 0),
        samples_by_type={name: [] for name in _FAILURE_ORDER},
        source_stats_by_type={},
        keyword_stats_by_type={},
    )
    for record in records:
        failure_type = record.failure_type
        if failure_type not in analysis.distribution:
            analysis.distribution[failure_type] = 0
            analysis.samples_by_type[failure_type] = []
        analysis.distribution[failure_type] += 1
        analysis.samples_by_type[failure_type].append(record.sample_id)
        sources = analysis.source_stats_by_type.setdefault(failure_type, Counter())
        involved = _involved_titles(record)
        sources.update(
            str(candidate.get("source", ""))
            for candidate in _involved_candidates(record)
        )
        keywords = analysis.keyword_stats_by_type.setdefault(failure_type, Counter())
        keywords.update(_keywords(involved))
    return analysis


def render_analysis(analysis: FailureAnalysis) -> str:
    """Render the analysis as a Markdown failure report."""
    lines = [
        "# 策展失败归因 (P64.2 T10)",
        "",
        f"- 输入报告: `{analysis.report}`",
        f"- 失败样本: {analysis.total_failed}",
        "",
        "## 五类分布",
        "",
        "| failure_type | 数量 | 样本 |",
        "|---|---:|---|",
    ]
    for failure_type in _FAILURE_ORDER:
        count = analysis.distribution.get(failure_type, 0)
        samples = ", ".join(analysis.samples_by_type.get(failure_type, []))
        lines.append(f"| {failure_type} | {count} | {samples} |")
    lines.append("")
    for failure_type in _FAILURE_ORDER:
        if analysis.distribution.get(failure_type, 0) == 0:
            continue
        sources = analysis.source_stats_by_type.get(failure_type, Counter())
        keywords = analysis.keyword_stats_by_type.get(failure_type, Counter())
        lines.append(f"## {failure_type}")
        lines.append("")
        if sources:
            top_sources = ", ".join(f"{name} x{count}" for name, count in sources.most_common(5))
            lines.append(f"- 涉及候选 Top 源: {top_sources}")
        if keywords:
            top_keywords = ", ".join(f"{name} x{count}" for name, count in keywords.most_common(8))
            lines.append(f"- 高频关键词: {top_keywords}")
        lines.append(f"- prompt 修改方向: {_PROMPT_ADVICE[failure_type]}")
        lines.append("")
    return "\n".join(lines)


def _involved_candidates(record: BadCaseRecord) -> list[dict[str, object]]:
    digest = record.candidates_digest
    false_negatives = cast("list[str]", digest.get("false_negatives", []))
    false_positives = cast("list[str]", digest.get("false_positives", []))
    involved_ids = set(false_negatives) | set(false_positives)
    candidates = digest.get("candidates", [])
    if not isinstance(candidates, list):
        return []
    involved = [c for c in candidates if isinstance(c, dict) and c.get("id") in involved_ids]
    return involved if involved else [
        c for c in candidates if isinstance(c, dict)
    ][:3]


def _involved_titles(record: BadCaseRecord) -> list[str]:
    return [
        str(candidate.get("title", ""))
        for candidate in _involved_candidates(record)
    ]


def _keywords(titles: list[str]) -> list[str]:
    tokens: list[str] = []
    for title in titles:
        lowered = title.casefold()
        tokens.extend(
            token for token in lowered.replace(",", " ").split() if len(token) >= 4
        )
    return tokens


__all__ = ["FailureAnalysis", "analyze_failures", "render_analysis"]
