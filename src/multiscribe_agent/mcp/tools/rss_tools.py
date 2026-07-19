"""MCP adapter trigger tool."""

from __future__ import annotations

from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.mcp.types import FetchRSSInput


async def fetch_rss(payload: dict[str, object], context: ServiceContext) -> dict[str, object]:
    """Run one configured adapter and return the newest persisted normalized entries."""
    params = FetchRSSInput.model_validate(payload)
    if context.ingestion is None or context.source_data is None:
        raise RuntimeError("ingestion service unavailable")
    count = await context.ingestion.run_single(params.adapter_id, params.config)
    items = await context.source_data.query({"limit": params.max_items})
    return {
        "adapter_id": params.adapter_id,
        "fetched_count": count,
        "items": [item.model_dump(mode="json") for item in items[: params.max_items]],
    }
