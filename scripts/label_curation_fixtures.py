"""Label fixtures with expected_selected_ids / expected_rejected_ids / schema_version.

Two modes:

1. Legacy (default, no flags):  write the 50 hard-coded labels for cr-001..cr-050
   produced during P57 Phase 1. Use --no-legacy to disable.

2. JSON-driven:  load labels from ``--labels-source FILE.json`` (a single object
   keyed by sample id) or from a directory of per-fixture JSON files when
   ``--labels-source`` points to a directory. This mode is what Phase 4 uses to
   promote the LLM-proposed labels into fixtures.

When ``--dry-run`` is set, no fixture is overwritten and the script just
validates the label set against each fixture's candidate IDs.
"""

import argparse
import glob
import json
from pathlib import Path

labels = {
    "cr-001": {
        "selected": ["cr-001-a4"],
        "rationale": "选中 1 条:Microsoft Autonomous RAG (AI 公司产品). 拒 9 条:OpenAI Academy 教程 x4, 纯数学 arXiv x2, BBC 体育, SW Orchestrions (非 AI), github_trending ChromeDevTools (工具而非 AI).",
    },
    "cr-002": {
        "selected": ["cr-002-a2", "cr-002-a3", "cr-002-a5"],
        "rationale": "选中 3 条:arXiv LLM self-correction (DeCRIM), AI 公司 agent framework (Gemini Agents), SW AI 工具评论 (Nativ). 拒 7 条:OpenAI Academy 教程 x4, BBC 影视, github_trending WhatsApp (非 AI), arXiv facial AU (纯 CV).",
    },
    "cr-003": {
        "selected": ["cr-003-a2", "cr-003-a6"],
        "rationale": "选中 2 条:Mistral Mixtral 开源 (AI 公司), arXiv MEDIC LLM safety. 拒 8 条:OpenAI Academy 教程 x4, BBC app, SW 海狮照片 (非 AI), github_trending ECC (描述含 Claude 但属工具, 拒以稳妥), arXiv Metareasoning (无 LLM 关键词), arXiv backup.",
    },
    "cr-004": {
        "selected": ["cr-004-a5", "cr-004-a7"],
        "rationale": "选中 2 条:arXiv LLM 医学诊断 (LLM Medical Diagnosis), arXiv RAG/hallucination (Hallucinations and Truth). 拒 8 条:OpenAI Academy 教程 x4, BBC 国际新闻, SW Orchestrions (非 AI), github_trending tuicr (代码 review TUI), arXiv Small LLMs (实为 perplexity), arXiv EFX Allocations (纯数学).",
    },
    "cr-005": {
        "selected": ["cr-005-a2", "cr-005-a6", "cr-005-a7"],
        "rationale": "选中 3 条:SW pelicanmaxxing (AI 实质评论), arXiv MedHallTune (VLM 医学), Hugging Face fine-tune library. 拒 7 条:OpenAI Academy 教程 x4, BBC 刑事, github_trending Ansible (非 AI), arXiv evidence fusion (纯统计).",
    },
    "cr-006": {
        "selected": ["cr-006-a1", "cr-006-a2", "cr-006-a5", "cr-006-a6"],
        "rationale": "选中 4 条:SW OpenAI cyberattack (AI 安全事件), github_trending openwork (Claude Cowork 开源), arXiv Machine-Generated Text Detection, AWS Bedrock RAG. 拒 6 条:OpenAI Academy 教程 x4, BBC 刑事, arXiv 机器人 TAMP (纯机器人学).",
    },
    "cr-007": {
        "selected": ["cr-007-a2", "cr-007-a4", "cr-007-a5", "cr-007-a7"],
        "rationale": "选中 4 条:arXiv Human+AI agent, arXiv CRMWeaver agentic RL, Meta Llama 4 开源, SW pentest LLM 评论. 拒 6 条:github_trending ASP.NET (非 AI), OpenAI Academy 教程 x4, BBC 家庭, OpenAI Applications (Academy).",
    },
    "cr-008": {
        "selected": ["cr-008-a1", "cr-008-a3", "cr-008-a4", "cr-008-a7"],
        "rationale": "选中 4 条:arXiv LLM 低精度训练, arXiv LLM 语言多样性, Stanford agent benchmark, github_trending Hugging Face speech-to-speech. 拒 6 条:OpenAI Academy 教程 x4, BBC 健康, SW PyPI (非 AI).",
    },
    "cr-009": {
        "selected": ["cr-009-a2", "cr-009-a3", "cr-009-a5", "cr-009-a6"],
        "rationale": "选中 4 条:arXiv LLM truth geometry, EleutherAI NeoX 开源, SW runaway AI agent, github_trending AI-For-Beginners. 拒 6 条:OpenAI Academy 教程 x4, BBC 名人, arXiv Responsible AI LEGO (纯社会科学), OpenAI Applications (Academy).",
    },
    "cr-010": {
        "selected": ["cr-010-a1", "cr-010-a2", "cr-010-a4"],
        "rationale": "选中 3 条:arXiv AfriEconQA (QA/benchmark), OpenAI GPT-5 发布, SW Anthropic Opus 5. 拒 7 条:OpenAI Academy 教程 x4, BBC 山火, github_trending PowerToys (非 AI), arXiv Eikonal Neural (纯几何).",
    },
    "cr-011": {
        "selected": ["cr-011-a1", "cr-011-a3", "cr-011-a4", "cr-011-a5", "cr-011-a7"],
        "rationale": "选中 5 条:Anthropic Claude 4 RAG, SW Opus 5 prompt injectable, github_trending last30days (AI agent), arXiv MemAgent LLM 记忆, arXiv LLM training data. 拒 5 条:OpenAI Academy 教程 x4, BBC 桥, OpenAI Financial Services (Academy).",
    },
    "cr-012": {
        "selected": ["cr-012-a4", "cr-012-a6", "cr-012-a7"],
        "rationale": "选中 3 条:arXiv LLM Fingerprinting (安全), arXiv medical multimodal RL, Cohere Command R+ RAG. 拒 7 条:OpenAI Academy 教程 x4, BBC 热浪, SW Ruff (非 AI), github_trending systematic trading (非 AI).",
    },
    "cr-013": {
        "selected": ["cr-013-a1", "cr-013-a5", "cr-013-a6"],
        "rationale": "选中 3 条:SW LLM tokens 黑产, arXiv MentorCollab reasoning, Anthropic Claude 4 tool-use. 拒 7 条:OpenAI Academy 教程 x4, BBC 战事, github_trending editor (非 AI), arXiv Homomorphic Encryption (纯加密), SW 引用 Linus (非 AI).",
    },
    "cr-014": {
        "selected": ["cr-014-a1", "cr-014-a2", "cr-014-a4", "cr-014-a5"],
        "rationale": "选中 4 条:github_trending aisuite (AI 工具), arXiv Ophthalmic MLLMs (医学 LLM), arXiv Language Models geometry, AutoGPT 2.0 发布. 拒 6 条:OpenAI Academy 教程 x4, BBC 刑事, SW sqlite-utils (非 AI release).",
    },
    "cr-015": {
        "selected": ["cr-015-a1", "cr-015-a3", "cr-015-a4", "cr-015-a7"],
        "rationale": "选中 4 条:arXiv HealthSLM LLM, arXiv GradMAP LLM, Hugging Face Agents Hub, github_trending claude-video. 拒 6 条:OpenAI Academy 教程 x4, BBC 私生活, SW 通用 AI 工具评论, OpenAI Applications (Academy).",
    },
    "cr-016": {
        "selected": ["cr-016-a2", "cr-016-a3", "cr-016-a5", "cr-016-a6"],
        "rationale": "选中 4 条:arXiv LLM2Vec embeddings, OpenAI GPT-5 发布, SW Moonshot Kimi K3, github_trending agent governance toolkit. 拒 6 条:OpenAI Academy 教程 x4, BBC 海滩, arXiv GBPP (纯机器人学).",
    },
    "cr-017": {
        "selected": ["cr-017-a1", "cr-017-a2", "cr-017-a4", "cr-017-a6"],
        "rationale": "选中 4 条:arXiv RewardBench LLM, DeepMind Gemini 3 开源, SW Modal/agent 安全事件, arXiv LoRA fine-tuning. 拒 6 条:OpenAI Academy 教程 x4, BBC 刑事, github_trending airi (Neuro-sama 边界, 拒以稳妥).",
    },
    "cr-018": {
        "selected": ["cr-018-a1", "cr-018-a3", "cr-018-a5", "cr-018-a7"],
        "rationale": "选中 4 条:LangGraph Studio (AI 公司), SW AI agent intrusion 事件, arXiv VideoLLM 文化, arXiv synthetic pretraining data. 拒 6 条:OpenAI Academy 教程 x4, BBC 慈善, github_trending GeoLibre (GIS, 非 AI).",
    },
    "cr-019": {
        "selected": ["cr-019-a2", "cr-019-a3", "cr-019-a4", "cr-019-a6", "cr-019-a7"],
        "rationale": "选中 5 条:SW Claude cryptography (Anthropic 安全), github_trending book-to-skill (Claude skill), arXiv ARC-Encoder (LLM 压缩), arXiv S-GRPO LVLM, DeepSeek-R1 开源. 拒 5 条:OpenAI Academy 教程 x4, BBC 关税, OpenAI Applications (Academy).",
    },
    "cr-020": {
        "selected": ["cr-020-a3", "cr-020-a5", "cr-020-a6"],
        "rationale": "选中 3 条:arXiv LLM persona evaluation, arXiv prompt injection detection, Cohere Command R+ RAG. 拒 7 条:OpenAI Academy 教程 x4, SW uv release (非 AI), github_trending superfile (非 AI), BBC 旅游税, OpenAI Applications (Academy).",
    },
    "cr-021": {
        "selected": ["cr-021-a4", "cr-021-a5", "cr-021-a7"],
        "rationale": "选中 3 条:arXiv HumorRank LLM, LlamaCloud (AI 公司), SW AI Worming Word (prompt injection). 拒 7 条:OpenAI Academy 教程 x4, github_trending Instatic (描述含 'agentic' 但实为 CMS), BBC 车祸, arXiv Morphogenesis (无 LLM), OpenAI Applications (Academy).",
    },
    "cr-022": {
        "selected": ["cr-022-a1", "cr-022-a3", "cr-022-a4"],
        "rationale": "选中 3 条:arXiv BioPro VLM 公平, arXiv NorBERTo ModernBERT, Meta Llama 4 70B 开源. 拒 7 条:OpenAI Academy 教程 x4, BBC 政治, SW D. Richard Hipp (非 AI), github_trending Chat2DB (数据库, 非 AI), OpenAI Applications (Academy).",
    },
    "cr-023": {
        "selected": ["cr-023-a2", "cr-023-a3"],
        "rationale": "选中 2 条:arXiv VISTA AI agent egocentric, Mistral CodeMistral 开源. 拒 8 条:OpenAI Academy 教程 x4, github_trending Pumpkin (Minecraft, 非 AI), SW Matthew Green (密码学, 非 AI), BBC 西岸, arXiv AMEND (临床, 无 LLM/agent), OpenAI Applications (Academy).",
    },
    "cr-024": {
        "selected": ["cr-024-a1", "cr-024-a2", "cr-024-a4", "cr-024-a5"],
        "rationale": "选中 4 条:arXiv Orchard agentic framework, Microsoft Phi-4, SW MCP Claude, github_trending Alibaba LLM code review. 拒 6 条:OpenAI Academy 教程 x4, BBC 政治, arXiv electromyography (纯医学信号), OpenAI Applications (Academy).",
    },
    "cr-025": {
        "selected": ["cr-025-a1", "cr-025-a5", "cr-025-a7"],
        "rationale": "选中 3 条:OpenAI GPT-5 agentic, arXiv AdaMARP LLM role-play, arXiv MinerU-Popo VLM. 拒 7 条:OpenAI Academy 教程 x4, BBC 理财, SW Bruce Schneier (非 AI 实质), github_trending amnezia-vpn (非 AI), OpenAI Applications (Academy).",
    },
    "cr-026": {
        "selected": ["cr-026-a4", "cr-026-a6", "cr-026-a7"],
        "rationale": "选中 3 条:arXiv TANDEM multimodal hate, arXiv MiniMax-M2 MoE LLM, CodeGemma RAG. 拒 7 条:OpenAI Academy 教程 x4, BBC 政治, SW llm-chat-completions (release, 非实质), github_trending claude-cookbooks (教程, 拒), OpenAI Applications (Academy).",
    },
    "cr-027": {
        "selected": ["cr-027-a5", "cr-027-a6"],
        "rationale": "选中 2 条:arXiv LLM annotation 评测, Mistral Large 3 RAG agent. 拒 8 条:OpenAI Academy 教程 x4, BBC 政治, SW llm release (非实质), github_trending buzz (非 AI), arXiv ROS 机器人 (纯机器人, 无 LLM), OpenAI Applications (Academy).",
    },
    "cr-028": {
        "selected": ["cr-028-a2", "cr-028-a4", "cr-028-a5"],
        "rationale": "选中 3 条:arXiv DialectLLM, arXiv MEDIAREF RAG, CrewAI 多 agent. 拒 7 条:OpenAI Academy 教程 x4, github_trending ego-lite (浏览器, 边界, 拒以稳妥), BBC 政治, SW llm release (非实质), OpenAI Applications (Academy).",
    },
    "cr-029": {
        "selected": ["cr-029-a3", "cr-029-a4", "cr-029-a6"],
        "rationale": "选中 3 条:arXiv LLM behavioural auditing, Gemma 2 RAG 开源, SW GPT-5.6 价格调整. 拒 7 条:OpenAI Academy 教程 x4, arXiv uncertainty (纯统计), BBC 中东, github_trending nodejs (非 AI), OpenAI Applications (Academy).",
    },
    "cr-030": {
        "selected": ["cr-030-a2", "cr-030-a3", "cr-030-a5", "cr-030-a6"],
        "rationale": "选中 4 条:arXiv Co-evolving LLM agent eval, Stanford AgentBench 2 开源, SW Anthropic cybersecurity, arXiv LLM A/B. 拒 6 条:OpenAI Academy 教程 x4, BBC 体育, github_trending impeccable (UI 工具, 非 AI).",
    },
    "cr-031": {
        "selected": ["cr-031-a1", "cr-031-a2", "cr-031-a4"],
        "rationale": "选中 3 条:arXiv LLM question-order, LangGraph Studio, SW GPT-5.6 file deletion bug. 拒 7 条:OpenAI Academy 教程 x4, BBC 体育, github_trending bitchat (蓝牙, 非 AI), arXiv CT 影像 (纯医学, 无 LLM 信号), OpenAI Applications (Academy).",
    },
    "cr-032": {
        "selected": ["cr-032-a1", "cr-032-a5", "cr-032-a7"],
        "rationale": "选中 3 条:Hugging Face Agent SDK v2, arXiv sycophancy LLM, arXiv MagicSelector agent tool. 拒 7 条:OpenAI Academy 教程 x4, BBC 体育, SW Firefox WebAssembly (非 AI), github_trending bitchat (非 AI), OpenAI Applications (Academy).",
    },
    "cr-033": {
        "selected": ["cr-033-a2", "cr-033-a4", "cr-033-a6", "cr-033-a7"],
        "rationale": "选中 4 条:SW Inkling open-weights (Thinking Machines), arXiv AI climate inequality, arXiv SLAI T-Rex LLM 训练, Microsoft AutoRAG. 拒 6 条:OpenAI Academy 教程 x4, BBC 体育, github_trending Kronos (金融, 拒以稳妥), OpenAI Applications (Academy).",
    },
    "cr-034": {
        "selected": ["cr-034-a1", "cr-034-a5", "cr-034-a6"],
        "rationale": "选中 3 条:SW Moonshot Kimi K3, arXiv LLM failure modes, Weaviate RAG. 拒 7 条:OpenAI Academy 教程 x4, github_trending harper (语法, 非 AI), arXiv enthymemes (纯 NLP, 无 LLM), BBC 体育, OpenAI Applications (Academy).",
    },
    "cr-035": {
        "selected": ["cr-035-a2", "cr-035-a4", "cr-035-a5", "cr-035-a7"],
        "rationale": "选中 4 条:arXiv MICA LLM RL, arXiv LLM reading/writing, Meta Llama 4 multimodal, SW Kimi K3 prompt leak. 拒 6 条:OpenAI Academy 教程 x4, github_trending claude-skills (资源列表, 拒以稳妥), BBC 体育, OpenAI Applications (Academy).",
    },
    "cr-036": {
        "selected": ["cr-036-a1", "cr-036-a3", "cr-036-a4"],
        "rationale": "选中 3 条:arXiv LVLM retinal, arXiv multi-agent fact-checking, Anthropic Claude 4 RAG. 拒 7 条:OpenAI Academy 教程 x4, BBC 体育, SW LLM cliché tool (非实质), github_trending dive-into-llms (教程), OpenAI Applications (Academy).",
    },
    "cr-037": {
        "selected": ["cr-037-a2", "cr-037-a3"],
        "rationale": "选中 2 条:arXiv HANDBOOK agentic instruction, CrewAI 融资. 拒 8 条:OpenAI Academy 教程 x4, BBC 天气, SW Spot birds (非 AI), github_trending turbovec (向量索引, 无 LLM), Stargate Infrastructure (企业稿, 拒), OpenAI Applications (Academy).",
    },
    "cr-038": {
        "selected": ["cr-038-a1", "cr-038-a2", "cr-038-a6"],
        "rationale": "选中 3 条:arXiv BM25 RAG scaling, PyTorch 3.0 LLM inference, arXiv multi-turn safety LLM. 拒 7 条:OpenAI Academy 教程 x4, BBC 政治, SW Claude Fable (产品, 拒以稳妥), github_trending skills (开发方法, 非 AI), OpenAI Applications (Academy).",
    },
    "cr-039": {
        "selected": ["cr-039-a1", "cr-039-a4", "cr-039-a5", "cr-039-a7"],
        "rationale": "选中 4 条:Mistral fine-tuning RAG, github_trending superpowers agent, arXiv LLM monitoring, arXiv constitutional midtraining. 拒 6 条:OpenAI Academy 教程 x4, BBC 政治, SW quixote (非 AI), OpenAI EU uptake (企业稿, 拒), OpenAI Applications (Academy).",
    },
    "cr-040": {
        "selected": ["cr-040-a4", "cr-040-a7"],
        "rationale": "选中 2 条:arXiv LLM metacognition, Microsoft Phi-4-Mini 开源. 拒 8 条:OpenAI Academy 教程 x4, BBC 政治, SW SQLite query tool (非实质), github_trending palmier-pro (视频, 拒以稳妥), arXiv concepts (边界), OpenAI Applications (Academy).",
    },
    "cr-041": {
        "selected": ["cr-041-a3", "cr-041-a6"],
        "rationale": "选中 2 条:arXiv GroupRAG, OpenAI GPT-5 agent 发布. 拒 8 条:OpenAI Academy 教程 x4, SW AI mania (评论, 边界), BBC 体育, github_trending Apollo-11 (非 AI), arXiv APEX-Accounting (纯会计, 无 LLM), OpenAI Applications (Academy).",
    },
    "cr-042": {
        "selected": ["cr-042-a2", "cr-042-a4", "cr-042-a5", "cr-042-a7"],
        "rationale": "选中 4 条:arXiv REAP coding agent, arXiv prompt chaining, MedRAX RAG, SW Claude Code Bun Rust. 拒 6 条:OpenAI Academy 教程 x4, BBC 天气, github_trending OmniRoute (API gateway, 拒以稳妥), OpenAI Argentina (企业稿, 拒).",
    },
    "cr-043": {
        "selected": ["cr-043-a3", "cr-043-a4"],
        "rationale": "选中 2 条:arXiv Arabic speech LLM therapy, Stability AI StableLM-2 开源. 拒 8 条:OpenAI Academy 教程 x4, arXiv quantum (纯量子), BBC 刑事, SW Chinese models (评论, 拒), github_trending worldmonitor (边界, 拒), OpenAI malicious report (企业稿).",
    },
    "cr-044": {
        "selected": ["cr-044-a2", "cr-044-a3"],
        "rationale": "选中 2 条:arXiv AI-assisted pre-review, Meta Llama 4 MoE 开源. 拒 8 条:OpenAI Academy 教程 x4, BBC 政治, SW reverse engineering (评论, 拒), github_trending likec4 (架构图, 非 AI), arXiv Von Economo (纯神经科学, 无 LLM), OpenAI malicious (企业稿).",
    },
    "cr-045": {
        "selected": ["cr-045-a2", "cr-045-a6"],
        "rationale": "选中 2 条:LangChain Agent SDK v2, arXiv LLM social swarm. 拒 8 条:OpenAI Academy 教程 x4, arXiv Sympathetic (纯 NLP), BBC 体育, SW Sam Altman 引用 (评论, 拒), github_trending RuView (WiFi, 拒), OpenAI EU (企业稿).",
    },
    "cr-046": {
        "selected": ["cr-046-a1", "cr-046-a4"],
        "rationale": "选中 2 条:Databricks 收购 RAGFlow, arXiv facial-expression LLM tutoring. 拒 8 条:OpenAI Academy 教程 x4, BBC 犯罪, SW Linus Torvalds (评论, 拒), arXiv THGFM (图模型, 无 LLM 信号), OpenAI intellectual freedom (企业稿).",
    },
    "cr-047": {
        "selected": ["cr-047-a5", "cr-047-a6"],
        "rationale": "选中 2 条:arXiv LayerRAG-Bench, Anthropic Claude agent 性能. 拒 8 条:OpenAI Academy 教程 x4, BBC 文化, SW mermaid-ascii (工具, 非实质), arXiv BioHiCL (纯生物医学检索, 无 LLM), OpenAI Government (企业稿, 拒).",
    },
    "cr-048": {
        "selected": ["cr-048-a2", "cr-048-a5"],
        "rationale": "选中 2 条:arXiv MathNet multimodal, HF OpenAgentBench. 拒 8 条:OpenAI Academy 教程 x4, SW mermaid-unicode (工具, 非实质), BBC 政治, arXiv BridgeAlign HSS (纯社科, 无 LLM/agent), OpenAI Intelligence Age (企业稿).",
    },
    "cr-049": {
        "selected": ["cr-049-a3", "cr-049-a4"],
        "rationale": "选中 2 条:arXiv Explorative Modeling pretraining, Stability AI StableLM 3B 开源. 拒 8 条:OpenAI Academy 教程 x4, arXiv ABPMS (纯业务流程), BBC 热浪, OpenAI Governor letter (企业稿, 拒), OpenAI Applications (Academy).",
    },
    "cr-050": {
        "selected": ["cr-050-a1", "cr-050-a4"],
        "rationale": "选中 2 条:arXiv Alignment Target, Cohere Command R+ v2 RAG. 拒 8 条:OpenAI Academy 教程 x4, arXiv HSS-Synth (纯社科, 无 LLM), BBC 政治, OpenAI economic analysis (企业稿, 拒).",
    },
}


fixtures_dir = Path("tests/eval/fixtures")
files = sorted(glob.glob(str(fixtures_dir / "cr_*.json")))

LEGACY_LABELED_AT = "2026-08-09"
LEGACY_SCHEMA_VERSION = 1
LEGACY_LABELED_BY = "zcode:P57-F1"


def _load_json_labels(source: Path) -> dict[str, dict[str, object]]:
    """Read labels either from a single JSON file or from a directory of files."""
    if source.is_dir():
        labels: dict[str, dict[str, object]] = {}
        for fp in sorted(source.glob("cr_*.json")):
            sample_id = fp.stem.replace("_", "-")
            payload = json.loads(fp.read_text(encoding="utf-8"))
            labels[sample_id] = payload
        return labels
    payload = json.loads(source.read_text(encoding="utf-8"))
    return {key.replace("_", "-"): value for key, value in payload.items()}


def _apply_labels(
    labels: dict[str, dict[str, object]],
    *,
    schema_version: int,
    labeled_by: str,
    labeled_at: str,
    dry_run: bool,
) -> int:
    count = 0
    for fp in files:
        name = Path(fp).stem  # cr_001
        sample_id = name.replace("_", "-")  # cr-001
        if sample_id not in labels:
            print(f"WARNING: no labels for {sample_id}")
            continue
        data = json.loads(open(fp, encoding="utf-8").read())
        label = labels[sample_id]
        selected = list(label.get("selected_ids") or label.get("selected") or [])
        all_ids = [c["id"] for c in data["candidates"]]
        candidate_set = set(all_ids)
        unknown = [sid for sid in selected if sid not in candidate_set]
        if unknown:
            raise ValueError(f"{sample_id}: selected_ids not in candidates: {unknown}")
        rejected = [cid for cid in all_ids if cid not in selected]
        data["expected_selected_ids"] = selected
        data["expected_rejected_ids"] = rejected
        data["selection_rationale"] = str(label.get("rationale", ""))
        data["schema_version"] = schema_version
        data["labeled_by"] = labeled_by
        data["labeled_at"] = labeled_at
        if not dry_run:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labels-source",
        type=Path,
        help="Path to labels.json or to a directory of per-fixture cr_NNN.json labels.",
    )
    parser.add_argument(
        "--schema-version",
        type=int,
        default=LEGACY_SCHEMA_VERSION,
        help="schema_version to write into each fixture (default: legacy 1).",
    )
    parser.add_argument(
        "--labeled-by",
        default=LEGACY_LABELED_BY,
        help="labeled_by value to stamp onto each fixture.",
    )
    parser.add_argument(
        "--labeled-at",
        default=LEGACY_LABELED_AT,
        help="labeled_at value to stamp onto each fixture.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate labels without writing back to fixtures.",
    )
    parser.add_argument(
        "--no-legacy",
        action="store_true",
        help="Skip the legacy hard-coded cr-001..cr-050 fallback when --labels-source is unset.",
    )
    args = parser.parse_args()

    if args.labels_source is None and not args.no_legacy:
        effective_labels = labels
        schema_version = LEGACY_SCHEMA_VERSION
        labeled_by = LEGACY_LABELED_BY
        labeled_at = LEGACY_LABELED_AT
    elif args.labels_source is not None:
        effective_labels = _load_json_labels(args.labels_source)
        schema_version = args.schema_version
        labeled_by = args.labeled_by
        labeled_at = args.labeled_at
    else:
        print("No labels source and --no-legacy given; nothing to do.")
        return

    count = _apply_labels(
        effective_labels,
        schema_version=schema_version,
        labeled_by=labeled_by,
        labeled_at=labeled_at,
        dry_run=args.dry_run,
    )
    mode = "validated" if args.dry_run else "labeled"
    print(f"{mode.capitalize()} {count} fixtures")


if __name__ == "__main__":
    main()
