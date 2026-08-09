"""Run eval-curation benchmark directly (no click CLI) so output is visible."""

import asyncio
import os
from pathlib import Path

os.environ.setdefault(
    "OPENAI_API_KEY",
    "sk-fcadc30fb288128554ac553ce46ab15654c219d885a830fce816cb27d1652117",
)
os.environ.setdefault("OPENAI_API_BASE_URL", "https://apizh-ai.com/v1")

from multiscribe_agent.cli import _resolve_eval_provider
from multiscribe_agent.config import get_settings
from multiscribe_agent.eval.curation_benchmark import run_curation_benchmark
from multiscribe_agent.eval.curation_dataset import load_curation_dataset


async def main() -> None:
    settings = get_settings()
    provider = _resolve_eval_provider(settings)
    print(f"Provider ready: {type(provider).__name__}", flush=True)
    dataset = load_curation_dataset(Path("data/eval/datasets/curation_recall.yaml"))
    print(f"Dataset loaded: {len(dataset.samples)} samples", flush=True)
    summary = await run_curation_benchmark(
        provider,
        dataset,
        reports_dir=Path("data/eval/reports"),
        baseline_path=Path("data/eval/baselines/curation_recall.json"),
        threshold=0.05,
        target_count=12,
    )
    print(
        f"\nFinal: {summary.dataset_name} precision={summary.avg_precision:.3f} "
        f"recall={summary.avg_recall:.3f} f1={summary.avg_f1:.3f} "
        f"passed={summary.passed}/{summary.total}",
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
