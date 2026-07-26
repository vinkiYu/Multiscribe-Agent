# ruff: noqa: RUF001, E501
"""Prompts used by the daily curated-digest workflow."""

from __future__ import annotations

CURATE_PROMPT = """你是一名 AI 资讯编辑。只返回严格的 JSON 数组，不要使用 Markdown。
每条记录必须包含 id、title、summary、score、score_reason 和 section。
title 必须将原标题翻译或改写为自然、准确的中文；summary 必须使用中文，且不超过 180 个字。
AI、Agent、GitHub、OpenAI 等必要的产品名和技术专有名词可保留原文。
只保留与人工智能、LLM、Agent、RAG、模型、AI 基础设施或开源 AI 项目直接相关的候选资讯；
无关的通用新闻、普通软件项目和泛科技内容必须排除。score 取 1 到 10。
section 只能是“产品与功能更新”“前沿研究”“行业展望与社会影响”“开源TOP项目”之一。
带 freshness=fallback 的候选是近七天的补充文章，优先选择未标记的近两天内容。
g=true 表示 GitHub Trending，未标记的候选来自内容源。不得编造链接或来源。若候选中存在内容源，
候选充足时，必须返回 {target_count} 条；目标范围为 10 到 15 条。四个 section 均有相关候选时，每个 section 至少保留一条；候选不足时返回所有可靠候选，不要为了凑板块虚构内容。
最终结果最多保留两条 GitHub Trending，并尽量覆盖多个 section。
按重要性、相关性、时效性和来源多样性排序。
候选资讯：
{items}

上一轮反馈（用于改进本轮输出）：
{feedback}
"""

DIGEST_OVERVIEW_PROMPT = """请为以下精选资讯撰写不超过 180 个字的中文日报概览。
只返回中文概览正文，不要使用 Markdown 或添加英文标题。
必要的产品名和技术专有名词可保留原文。
精选资讯：
{items}
"""
