"""Phase 7: label tightening via per-fixture LLM re-proposal.

Use the tighter prompt (select 1-4 with strict criteria) but cap each
proposal to the Phase-1 average of 2.9 selections. If the LLM proposes
more than the cap, keep the highest-scored ones (we approximate score
by ordering: AI company news > arXiv AI > GitHub AI > SW AI > TLDR AI > others).
"""
from __future__ import annotations

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

PROMPT_TEMPLATE = """对以下策展候选池做选/拒标注, 输出严格 JSON 对象:
{{
  "selected_ids": ["cr-NNN-aK", ...],   // 必须出现在 candidates 里, 选 1-4 条
  "rationale": "用 1-2 句中文解释为什么这样标注。"
}}

【判断标准】
- 选: 内容是 AI 行业新进展, 信息量高于标题本身, 适合 AI 资讯日报读者画像
- 优先选 arXiv 含 LLM/agent/RAG/model/multimodal 关键词; AI 公司产品发布; GitHub Trending AI 工具(含 Claude/LLM/agent); Simon Willison 评论含具体 AI 产品/事件
- 拒: OpenAI Academy 教程; 非 AI BBC; 非 AI GitHub Trending; 非 AI SW 评论; 与 AI 无关条目

candidates:
{candidates_json}
"""

# Tier priority for tie-breaking when proposal has too many
SOURCE_TIER = {
    "cs.AI updates on arXiv.org": 1,
    "cs.CL updates on arXiv.org": 1,
    "ai_search:perplexity": 2,
    "github_trending": 3,
    "Simon Willison's Weblog": 4,
    "OpenAI News": 5,
    "Hugging Face Daily Papers": 6,
    "TLDR AI": 7,
    "Last Week in AI": 8,
    "Hacker News": 9,
    "BBC News": 100,
}


def _trim(proposal: dict[str, object], cap: int = 2) -> dict[str, object]:
    """Trim proposal to <= cap selections, keeping highest-tier sources."""
    selected = list(proposal.get("selected_ids", []))
    if len(selected) <= cap:
        return proposal
    # We need full candidate list to rank by tier. Caller passes it via metadata.
    ranked = proposal.get("_ranked_candidates")
    if not ranked:
        # Without ranked candidates, just truncate.
        return {**proposal, "selected_ids": selected[:cap]}
    selected_set = set(selected)
    ranked_selected = [c["id"] for c in ranked if c["id"] in selected_set]
    return {**proposal, "selected_ids": ranked_selected[:cap]}


async def propose_one(sample_id: str, candidates: list[dict[str, object]], provider, cap: int = 2) -> dict[str, object] | None:
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
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match is None:
            return None
        proposal = json.loads(match.group(0))
    except Exception:
        return None
    candidate_ids = {c["id"] for c in candidates}
    valid_selected = [sid for sid in proposal.get("selected_ids", []) if sid in candidate_ids]
    if not valid_selected:
        return None
    # Rank candidates by source tier
    ranked = sorted(candidates, key=lambda c: (SOURCE_TIER.get(c["source"], 99), -len(c.get("description", ""))))
    trimmed = _trim({**proposal, "_ranked_candidates": ranked}, cap=cap)
    return {"selected_ids": trimmed["selected_ids"], "rationale": str(proposal.get("rationale", ""))[:200], "sample_id": sample_id}


async def main() -> None:
    settings = get_settings()
    provider = _resolve_eval_provider(settings)
    PROPOSAL_DIR.mkdir(parents=True, exist_ok=True)
    # Process cr-051..cr-100 only (new 50)
    for offset in range(51, 101):
        sample_id = f"cr-{offset:03d}"
        fixture_path = FIXTURES_DIR / f"cr_{offset:03d}.json"
        if not fixture_path.is_file():
            continue
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        proposal = await propose_one(sample_id, data["candidates"], provider, cap=2)
        if proposal is None:
            print(f"{sample_id}: SKIP")
            continue
        proposal_path = PROPOSAL_DIR / f"cr_{offset:03d}.json"
        proposal_path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{sample_id}: proposed ({len(proposal['selected_ids'])} selected)")


if __name__ == "__main__":
    asyncio.run(main())