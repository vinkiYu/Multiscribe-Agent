"""Public redirect endpoint for tracking daily-digest article clicks."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.bootstrap import ServiceContext

router = APIRouter(tags=["tracking"])


@router.get("/api/track-click", response_class=RedirectResponse)
async def track_click(
    request: Request,
    digest_date: str = Query(..., min_length=1),
    item_url: str | None = Query(default=None),
    item_source: str | None = Query(default=None),
    item_tags: str = Query(default=""),
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> RedirectResponse:
    """Record an anonymous click and redirect to its original HTTP(S) URL."""
    if not item_url or not item_url.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="item_url is required")
    parsed = urlparse(item_url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="item_url must be HTTP(S)"
        )
    if context.db is None or context.click_events is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="services unavailable"
        )
    tags = [tag.strip() for tag in item_tags.split(",") if tag.strip()]
    await context.click_events.record(
        context.db,
        digest_date=digest_date,
        item_url=item_url,
        item_source=item_source,
        item_tags=tags,
        user_agent=request.headers.get("user-agent"),
        referer=request.headers.get("referer"),
    )
    return RedirectResponse(url=item_url, status_code=status.HTTP_302_FOUND)
