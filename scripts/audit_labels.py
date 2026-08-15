"""Run the second-LLM label audit over a fixture sample (P64.2 T8)."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

os.environ.setdefault(
    "OPENAI_API_KEY",
    "sk-fcadc30fb288128554ac553ce46ab15654c219d885a830fce816cb27d1652117"
)
os.environ.setdefault("OPENAI_API_BASE_URL", "https://apizh-ai.com/v1")
os.environ.setdefault("DEFAULT_CURATION_MODEL", "gpt-5.4")
# .env proxy points at a dead local port; the relay is directly reachable.
os.environ["HTTP_PROXY"] = ""

from multiscribe_agent.cli import _resolve_eval_provider
from multiscribe_agent.config import get_settings
from multiscribe_agent.eval.cleaner.label_auditor import LabelAuditor
from multiscribe_agent.eval.curation_dataset import load_curation_dataset


async def run(args: argparse.Namespace) -> None:
    provider = _resolve_eval_provider(get_settings())
    dataset = load_curation_dataset(Path(args.dataset))
    auditor = LabelAuditor(provider, seed=args.seed)
    picked = auditor.pick_samples(dataset.samples, args.ratio)
    print(f"auditing {len(picked)} samples: {[s.id for s in picked]}")
    disputes = await auditor.audit(dataset.samples, ratio=args.ratio)
    target = auditor.write(disputes, Path(args.out))
    print(f"disputes={len(disputes)} -> {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/eval/datasets/curation_recall.yaml")
    parser.add_argument("--ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=64)
    parser.add_argument("--out", default="data/eval/label_disputes")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
