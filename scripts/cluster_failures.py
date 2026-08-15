"""Cluster failed samples with relay embeddings or a TF-IDF fallback (P64.2 T11)."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from multiscribe_agent.eval.clustering import EmbeddingClient, cosine, kmeans
from multiscribe_agent.eval.collector.bad_case import BadCaseCollector


def latest_report(reports_dir: Path) -> Path:
    reports = sorted(reports_dir.glob("curation-recall_*.md"))
    if not reports:
        raise SystemExit(f"no curation-recall report under {reports_dir}")
    return reports[-1]


async def run(args: argparse.Namespace) -> Path:
    out_dir = cast("Path", args.out)
    report = cast("Path", args.report) if args.report else latest_report(out_dir)
    fixtures_dir = cast("Path", args.fixtures)
    collector = BadCaseCollector(fixtures_dir)
    records = collector.collect(report, threshold=float(args.threshold))
    if not records:
        raise SystemExit("no failed samples to cluster")

    texts: list[str] = []
    titles_by_record: list[list[str]] = []
    for record in records:
        digest = record.candidates_digest
        false_negatives = cast("list[str]", digest.get("false_negatives", []))
        false_positives = cast("list[str]", digest.get("false_positives", []))
        involved = set(false_negatives) | set(false_positives)
        candidates = cast("list[dict[str, object]]", digest.get("candidates", []))
        titles = [
            str(candidate.get("title", ""))
            for candidate in candidates
            if candidate.get("id") in involved
        ]
        if not titles:
            titles = [str(candidate.get("title", "")) for candidate in candidates][:3]
        texts.append(" ".join(titles) or record.sample_id)
        titles_by_record.append(titles)

    client = EmbeddingClient(cache_dir=Path("data/eval/embedding_cache"))
    probe_ok = await client.probe()
    source = "relay:text-embedding-3-small" if probe_ok else "fallback:tfidf-char-ngram"
    vectors = await client.embed(texts)
    result = kmeans(vectors, k=int(args.k))

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"failure-clusters_{timestamp}.md"
    lines = [
        "# 失败样本聚类 (P64.2 T11)",
        "",
        f"- 输入报告: `{report}`",
        f"- 失败样本: {len(records)}",
        f"- 向量来源: {source}",
        f"- k = {result.k}",
        "",
    ]
    for cluster in range(result.k):
        members = [
            index for index, label in enumerate(result.labels) if label == cluster
        ]
        if not members:
            continue
        ranked = sorted(
            members,
            key=lambda index: -cosine(vectors[index], result.centroids[cluster]),
        )
        lines.append(f"## 簇 {cluster + 1} ({len(members)} 样本)")
        lines.append("")
        for index in ranked[:3]:
            lines.append(f"- 代表样本: {records[index].sample_id}")
            for title in titles_by_record[index][:3]:
                lines.append(f"  - 候选: {title}")
        lines.append("")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"source={source} k={result.k} clusters={result.k}")
    print(target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--fixtures", type=Path, default=Path("tests/eval/fixtures"))
    parser.add_argument("--threshold", type=float, default=0.7)
    parser.add_argument("--k", type=int, default=4, help="cluster count (plan: 3-5)")
    parser.add_argument("--out", type=Path, default=Path("data/eval/reports"))
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
