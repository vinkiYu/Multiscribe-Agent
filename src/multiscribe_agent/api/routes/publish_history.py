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
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> list[dict[str, object]]:
    """Return persisted outcomes, newest first, for authorized callers."""
    if context.db is None or context.publish_history is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    records = await context.publish_history.query(
        context.db,
        publisher_id=publisher_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
    )
    return [_record_to_response(record) for record in records]


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
