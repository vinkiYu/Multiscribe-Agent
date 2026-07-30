"""Authenticated full-text search over collected source data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.domain.models import SourceData

router = APIRouter(
    prefix="/api/source-data",
    tags=["source-data"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/search")
async def search_source_data(
    q: str = Query(..., max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> list[dict[str, object]]:
    """Return highlighted FTS results for an operator query."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="query cannot be empty")
    if context.source_data is None:
        raise HTTPException(status_code=503, detail="source_data unavailable")
    try:
        rows = await context.source_data.search_fts(q, limit=limit)
    except Exception:
        # FTS MATCH syntax is user-controlled; malformed expressions are empty results.
        return []
    return [_source_data_to_dict(row) for row in rows]


def _source_data_to_dict(row: SourceData) -> dict[str, object]:
    """Serialize only the fields needed by the search result view."""
    return {
        "id": row.id,
        "title": row.title,
        "url": row.url,
        "description": row.description,
        "source": row.source,
        "category": row.category,
        "published_date": row.published_date,
        "ingestion_date": row.ingestion_date,
        "adapter_name": row.adapter_name,
    }
