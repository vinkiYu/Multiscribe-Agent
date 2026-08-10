"""Ask the configured LLM to propose ground-truth labels for one fixture.

Outputs a single JSON file per fixture under ``data/eval/proposed_labels/`` so
humans can review each proposal before promoting it to the fixture itself.

Usage:
    python scripts/propose_labels_llm.py --start-index 51 --end-index 100
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault(
    "OPENAI_API_KEY",
    "sk-fcadc30fb288128554ac553ce46ab15654c219d885a830fce816cb27d1652117",
)
os.environ.setdefault("OPENAI_API_BASE_URL", "https://apizh-ai.com/v1")
os.environ.setdefault("HTTP_PROXY", "")

from multiscribe_agent.cli import _resolve_eval_provider
from multiscribe_agent.config import get_settings
from multiscribe_agent.domain.models import AIMessage

PROPOSAL_DIR = PROJECT_ROOT / "data" / "eval" / "proposed_labels"
FIXTURES_DIR = PROJECT_ROOT / "tests" / "eval" / "fixtures"

SYSTEM_INSTRUCTION = (
    "你是一名资深的 AI 资讯策展评审, 标注每条候选是否应该出现在一份面向 AI 从业者的精选日报里。"
    " 严格使用 JSON 输出。"
)

PROMPT_TEMPLATE = """对以下策展候选池做选/拒标注,输出严格 JSON 对象:
{{
  "selected_ids": ["cr-NNN-aK", ...],   // 必须出现在 candidates 里, 选 ≥ 1 条
  "rationale": "用 1-2 句中文解释为什么这样标注。候选充足时选 2-4 条;候选全是干扰时选最相关的 1 条。"
}}

【判断标准】
- 选:arXiv 含 LLM/agent/RAG/model/multimodal 关键词;AI 公司产品发布;GitHub Trending AI 工具(含 Claude/LLM/agent 描述);Simon Willison 评论含具体 AI 产品/事件;TLDR AI 含模型/工具/产品名
- 拒:OpenAI Academy 教程(Brainstorming/ChatGPT Sites/How to use);非 AI BBC;非 AI GitHub Trending([Rust]/[Shell]/[Assembly] 等且无 AI 关键词);非 AI SW 评论;TLDR AI 全是 emoji 标题且无具体 AI 产品

candidates:
{candidates_json}
"""


async def propose_one(sample_id: str, candidates: list[dict[str, object]], provider) -> dict[str, object] | None:
    """Ask the LLM to label one pool. Returns parsed JSON or None on failure."""
    payload = [
        {"id": c["id"], "title": c["title"], "description": c.get("description", ""), "source": c["source"]}
        for c in candidates
    ]
    prompt = PROMPT_TEMPLATE.format(candidates_json=json.dumps(payload, ensure_ascii=False, indent=2))
    try:
        response = await provider.generate(
            [AIMessage(role="user", content=prompt)],
            system_instruction=SYSTEM_INSTRUCTION,
        )
        text = response.content.strip()
        # Strip markdown fences if present.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match is None:
            return None
        proposal = json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        return None
    candidate_ids = {c["id"] for c in candidates}
    valid_selected = [sid for sid in proposal.get("selected_ids", []) if sid in candidate_ids]
    if not valid_selected:
        return None
    proposal["selected_ids"] = valid_selected
    proposal["sample_id"] = sample_id
    return proposal


async def main(args: argparse.Namespace) -> None:
    settings = get_settings()
    provider = _resolve_eval_provider(settings)
    PROPOSAL_DIR.mkdir(parents=True, exist_ok=True)
    for offset in range(args.start_index, args.end_index + 1):
        sample_id = f"cr-{offset:03d}"
        fixture_path = FIXTURES_DIR / f"cr_{offset:03d}.json"
        if not fixture_path.is_file():
            print(f"{sample_id}: SKIP (no fixture)")
            continue
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        proposal = await propose_one(sample_id, data["candidates"], provider)
        if proposal is None:
            print(f"{sample_id}: SKIP (LLM failure or no valid selection)")
            continue
        proposal_path = PROPOSAL_DIR / f"cr_{offset:03d}.json"
        proposal_path.write_text(
            json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{sample_id}: proposed ({len(proposal['selected_ids'])} selected)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-index", type=int, default=51)
    parser.add_argument("--end-index", type=int, default=100)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))