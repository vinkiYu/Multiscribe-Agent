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

_VALID_STATUSES = frozenset({"curated", "ignored", "published"})


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


@router.post("/batch-status")
async def batch_update_status(
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Bulk-transition the curation status of source-data rows."""
    if context.source_data is None:
        raise HTTPException(status_code=503, detail="source_data unavailable")
    ids = payload.get("ids")
    status = payload.get("status")
    if (
        not isinstance(ids, list)
        or not ids
        or not all(isinstance(item, str) and item for item in ids)
    ):
        raise HTTPException(status_code=400, detail="ids must be a non-empty string list")
    if not isinstance(status, str) or status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {sorted(_VALID_STATUSES)}",
        )
    updated = await context.source_data.update_status(ids, status)
    return {"status": status, "updated": updated, "ids": ids}


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
