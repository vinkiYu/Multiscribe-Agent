"""Run curation eval on a specified model by overriding default_curation_model.

Usage:
    OPENAI_API_KEY=... python scripts/run_eval_curation_model.py gpt-4o-mini
    OPENAI_API_KEY=... python scripts/run_eval_curation_model.py gpt-4o
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault(
    "OPENAI_API_KEY",
    "sk-fcadc30fb288128554ac553ce46ab15654c219d885a830fce816cb27d1652117",
)
os.environ.setdefault("OPENAI_API_BASE_URL", "https://apizh-ai.com/v1")
os.environ.setdefault("HTTP_PROXY", "")

from multiscribe_agent.cli import _resolve_eval_provider
from multiscribe_agent.config import get_settings
from multiscribe_agent.eval.curation_benchmark import run_curation_benchmark
from multiscribe_agent.eval.curation_dataset import load_curation_dataset


async def main(model: str) -> None:
    settings = get_settings()
    # Patch model for this run only.
    object.__setattr__(settings, "default_curation_model", model)
    provider = _resolve_eval_provider(settings)
    print(f"Provider ready: {type(provider).__name__} (model={model})", flush=True)
    dataset = load_curation_dataset(Path("data/eval/datasets/curation_recall.yaml"))
    print(f"Dataset loaded: {len(dataset.samples)} samples", flush=True)
    summary = await run_curation_benchmark(
        provider,
        dataset,
        reports_dir=Path("data/eval/reports"),
        baseline_path=None,
        threshold=1.0,  # never trigger regression
        target_count=12,
    )
    print(
        f"\n[{model}] precision={summary.avg_precision:.3f} "
        f"recall={summary.avg_recall:.3f} f1={summary.avg_f1:.3f} "
        f"passed={summary.passed}/{summary.total}",
        flush=True,
    )


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt-4o-mini"
    asyncio.run(main(model))