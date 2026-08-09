"""Diagnose why a sample was scored 0.000 — print all candidate titles with selected flag."""

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
from multiscribe_agent.eval.curation_benchmark import run_curation
from multiscribe_agent.eval.curation_dataset import load_curation_dataset


async def diagnose(sample_id: str) -> None:
    settings = get_settings()
    provider = _resolve_eval_provider(settings)
    dataset = load_curation_dataset(Path("data/eval/datasets/curation_recall.yaml"))
    for s in dataset.samples:
        if s.id == sample_id:
            sample = s
            break
    else:
        print(f"Sample {sample_id} not found")
        return
    selected = await run_curation(provider, sample, target_count=12)
    expected = set(sample.expected_selected_ids)
    print(f"\n=== {sample.id} ===")
    print(f"Expected: {sorted(expected)}")
    print(f"Model:    {sorted(selected)}")
    print(f"TP:       {sorted(selected & expected)}")
    print(f"FP:       {sorted(selected - expected)}")
    print(f"FN:       {sorted(expected - selected)}")
    print()
    print("All candidates (with model selected / expected selected):")
    for c in sample.candidates:
        flags = []
        if c.id in selected:
            flags.append("MODEL-SELECTED")
        if c.id in expected:
            flags.append("EXPECTED-SELECTED")
        print(f"  {c.id} [{c.source:30s}] {(' '.join(flags)):25s} | {c.title[:60]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: diagnose_sample.py cr-014")
    else:
        asyncio.run(diagnose(sys.argv[1]))
