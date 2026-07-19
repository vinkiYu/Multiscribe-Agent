"""MCP tool for read-only publish-history lookup."""

from __future__ import annotations

from datetime import datetime

from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.mcp.types import DigestHistoryInput


async def digest_history(payload: dict[str, object], context: ServiceContext) -> dict[str, object]:
    """Return bounded normalized delivery outcomes without exposing credentials."""
    params = DigestHistoryInput.model_validate(payload)
    if context.db is None or context.publish_history is None:
        raise RuntimeError("publish-history service unavailable")
    records = await context.publish_history.query(
        context.db,
        publisher_id=params.publisher_id,
        from_date=datetime.fromisoformat(params.from_date) if params.from_date else None,
        to_date=datetime.fromisoformat(params.to_date) if params.to_date else None,
        limit=params.limit,
    )
    return {
        "records": [
            {
                "id": record.id,
                "publisher_id": record.publisher_id,
                "status": record.status,
                "title": record.title,
                "content_preview": record.content_preview,
                "result_data": record.result_data,
                "error_message": record.error_message,
                "published_at": record.published_at.isoformat(),
                "adapter_name": record.adapter_name,
            }
            for record in records
        ]
    }
