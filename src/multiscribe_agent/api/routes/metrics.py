"""Prometheus-compatible metrics scrape endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Response

from multiscribe_agent.observability.meter import get_metrics_registry

router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Return standard text exposition, including no-op counters when degraded."""
    return Response(content=get_metrics_registry().render_prometheus(), media_type="text/plain")
