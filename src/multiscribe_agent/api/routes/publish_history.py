"""Authenticated read-only API for publisher delivery history."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.core.publish_history import PublishRecord

router = APIRouter(
    prefix="/api/publish-history",
    tags=["publish-history"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
async def list_publish_history(
    publisher_id: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Return persisted outcomes, newest first, for authorized callers."""
    if context.db is None or context.publish_history is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    total = await context.publish_history.count(
        context.db,
        publisher_id=publisher_id,
        from_date=from_date,
        to_date=to_date,
    )
    records = await context.publish_history.query(
        context.db,
        publisher_id=publisher_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
    return {
        "records": [_record_to_response(record) for record in records],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(records) < total,
    }


@router.get("/summary")
async def publish_history_summary(
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Return aggregate delivery counts for an optional date window."""
    if context.db is None or context.publish_history is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    return await context.publish_history.summary(context.db, from_date, to_date)


def _record_to_response(record: PublishRecord) -> dict[str, object]:
    """Serialize one typed record without exposing database implementation details."""
    return {
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
