"""MCP tool for P16 knowledge-base search."""

from __future__ import annotations

from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.mcp.types import KBSearchInput


async def knowledge_search(
    payload: dict[str, object], context: ServiceContext
) -> dict[str, object]:
    """Search the current knowledge base and return RRF provenance to MCP clients."""
    params = KBSearchInput.model_validate(payload)
    if context.kb_service is None:
        raise RuntimeError("knowledge-base service unavailable")
    hits = await context.kb_service.search(
        params.query, top_k=params.top_k, category_id=params.category_id
    )
    return {
        "hits": [
            {
                "chunk_id": hit.chunk_id,
                "document_id": hit.document_id,
                "content": hit.content,
                "score": hit.score,
                "source": hit.source,
            }
            for hit in hits
        ],
        "degraded": context.kb_service.capabilities.degraded,
        "capabilities": context.kb_service.capabilities.as_dict(),
    }
