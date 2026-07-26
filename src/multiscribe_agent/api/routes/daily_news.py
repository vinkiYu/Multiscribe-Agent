"""Public read-only API for the generated daily AI news archive."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.core.daily_digest_archive import ArchivedDigest, get_daily_digest_archive

router = APIRouter(prefix="/api/daily-news", tags=["daily-news"])


@router.get("")
async def read_daily_news(
    digest_date: Annotated[date | None, Query(alias="date")] = None,
    limit: Annotated[int, Query(ge=1, le=366)] = 31,
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Return archive navigation and the requested, or latest, complete digest."""
    if context.db is None:
        raise HTTPException(status_code=503, detail="services unavailable")

    archive = get_daily_digest_archive()
    records = await archive.list(context.db, limit=limit)
    selected: ArchivedDigest | None
    if digest_date is not None:
        selected = await archive.get(context.db, digest_date.isoformat())
        if selected is None:
            raise HTTPException(status_code=404, detail="daily digest not found")
    else:
        selected = records[0] if records else None

    return {
        "archives": [
            {
                "date": record.date,
                "title": record.title,
                "item_count": len(record.items),
                "updated_at": record.updated_at.isoformat(),
            }
            for record in records
        ],
        "digest": _serialize_digest(selected) if selected is not None else None,
    }


def _serialize_digest(record: ArchivedDigest) -> dict[str, object]:
    """Serialize only fields intentionally published on the public reading page."""
    return {
        "date": record.date,
        "title": record.title,
        "summary": record.summary,
        "items": [
            {
                "title": item.title,
                "summary": item.summary,
                "url": item.url,
                "source": item.source,
                "score": item.score,
                "image_url": item.image_url,
                "video_url": item.video_url,
                "published_at": item.published_at,
                "section": item.section,
                "tags": list(item.tags),
            }
            for item in record.items
        ],
        "total_scanned": record.total_scanned,
        "updated_at": record.updated_at.isoformat(),
    }
