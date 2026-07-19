"""Rubric prompt templates for LLM-as-Judge scoring."""

SUMMARY_RUBRIC = """You are evaluating a Chinese newsletter summary produced by an AI Agent.
Rate the following three dimensions on a 1-10 scale (integers only):

1. accuracy (事实准确性; 是否与原文一致, 无捏造)
2. conciseness (简洁性; 是否去除冗余, 信息密度高)
3. format (格式规范性; 是否符合 Markdown 标题/列表/段落规范)

Return ONLY JSON: {"accuracy":N,"conciseness":N,"format":N,"overall":N}
where overall = round((accuracy + conciseness + format) / 3)."""

RELEVANCE_RUBRIC = """Evaluate recommendation relevance between user preferences and selected items.

User preferred_tags: {tags}
Selected items tags: {item_tags}

Return ONLY JSON: {{"relevance":N,"matched":N,"total":N,"reason":"..."}}
where relevance = matched / total * 10 (integer, 0-10)."""

STABILITY_RUBRIC = """Evaluate the stability of the pipeline run based on log evidence.

Stats: {stats}

Return ONLY JSON: {{"stability":N,"bottleneck":"...","reason":"..."}}
where stability = weighted score (RSS 30% + LLM 40% + Publish 30%), integer 0-10."""
