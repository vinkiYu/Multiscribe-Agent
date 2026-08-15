"""Concurrency sweep for the parallel curation benchmark (P64.2 T9).

Runs the first N samples of the dataset at each concurrency level, records wall
time, throughput, avg tokens, and provider errors, and appends a Markdown
table so the optimal default can be written into MetricThresholds (T14).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault(
    "OPENAI_API_KEY",
    "sk-fcadc30fb288128554ac553ce46ab15654c219d885a830fce816cb27d1652117"
)
os.environ.setdefault("OPENAI_API_BASE_URL", "https://apizh-ai.com/v1")
os.environ.setdefault("DEFAULT_CURATION_MODEL", "gpt-5.4")
os.environ["HTTP_PROXY"] = ""

from multiscribe_agent.cli import _resolve_eval_provider
from multiscribe_agent.config import get_settings
from multiscribe_agent.eval.curation_benchmark import run_curation_benchmark
from multiscribe_agent.eval.curation_dataset import CurationDataset, load_curation_dataset


async def run(args: argparse.Namespace) -> None:
    provider = _resolve_eval_provider(get_settings())
    full = load_curation_dataset(Path(args.dataset))
    dataset = CurationDataset(
        name=f"{full.name}-sweep",
        description=full.description,
        samples=full.samples[: args.samples],
    )
    print(f"provider={type(provider).__name__} samples={len(dataset.samples)}")

    rows: list[tuple[int, float, float, int]] = []
    for concurrency in args.levels:
        start = time.perf_counter()
        try:
            summary = await run_curation_benchmark(
                provider,
                dataset,
                reports_dir=Path(args.out) / "sweep",
                concurrency=concurrency,
            )
            errors = 0
            f1 = summary.avg_f1
            tokens = summary.avg_tokens
        except Exception as exc:
            errors = 1
            f1 = 0.0
            tokens = 0
            print(f"concurrency={concurrency} failed: {exc}")
        elapsed = time.perf_counter() - start
        throughput = len(dataset.samples) / elapsed if elapsed else 0.0
        rows.append((concurrency, elapsed, throughput, tokens))
        print(
            f"concurrency={concurrency} elapsed={elapsed:.1f}s "
            f"throughput={throughput:.2f}/s errors={errors} f1={f1:.3f} avg_tokens={tokens}"
        )

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = Path(args.out) / f"concurrency-sweep_{timestamp}.md"
    lines = [
        "# 并发压测 (P64.2 T9)",
        "",
        f"- 样本数/轮: {len(dataset.samples)}",
        "",
        "| N | 耗时(s) | 吞吐(样本/s) | avg_tokens |",
        "|---:|---:|---:|---:|",
    ]
    lines.extend(
        f"| {n} | {elapsed:.1f} | {throughput:.2f} | {tokens} |"
        for n, elapsed, throughput, tokens in rows
    )
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/eval/datasets/curation_recall.yaml")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--levels", type=int, nargs="+", default=[2, 4, 8])
    parser.add_argument("--out", default="data/eval/reports")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
