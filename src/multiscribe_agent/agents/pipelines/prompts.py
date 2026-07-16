"""Prompts used by the daily curated-digest workflow."""

from __future__ import annotations

CURATE_PROMPT = """You are a news editor. Return a strict JSON array only, without Markdown.
Every item must include id, title, summary, score, and score_reason.
Score is a number from 1 to 10. Write a Chinese summary of at most 100 characters.
Rank importance and relevance, preserve facts, and never invent links or sources.
Candidate items:
{items}

Previous feedback (use it to improve the next response):
{feedback}
"""

DIGEST_OVERVIEW_PROMPT = """Write a Chinese daily-news overview of at most 100 characters.
Return overview text only.
Selected items:
{items}
"""
