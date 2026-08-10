"""Run ingestion for the four Phase 4 RSS adapters (HF/TLDR/HN/LWiAI).

Ingest each adapter into the runtime ``source_data`` table using its
registered ``metadata.id`` and the defaults baked into the adapter subclass.
Falls back gracefully when an endpoint is unreachable so the rest of the
sources still write through.

Usage:
    python scripts/ingest_new_rss.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

# Ensure the project root is on the import path and route through the
# configured OpenAI-compatible relay for any incidental LLM dependency.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault(
    "OPENAI_API_KEY",
    "sk-fcadc30fb288128554ac553ce46ab15654c219d885a830fce816cb27d1652117",
)
os.environ.setdefault("OPENAI_API_BASE_URL", "https://apizh-ai.com/v1")

from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import get_settings

NEW_RSS_ADAPTER_IDS = (
    "hf_daily_papers",
    "tldr_ai",
    "hacker_news",
    "last_week_in_ai",
)


async def main() -> None:
    settings = get_settings()
    ctx = ServiceContext(settings)
    await ctx.init()
    try:
        for adapter_id in NEW_RSS_ADAPTER_IDS:
            try:
                inserted = await ctx.ingestion.run_single(adapter_id, {})
                print(f"{adapter_id}: inserted={inserted}")
            except Exception as exc:  # noqa: BLE001
                print(f"{adapter_id}: ERROR {type(exc).__name__}: {exc}")
    finally:
        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())