"""Dashboard statistics, recent logs, and manual ingestion endpoints."""
# ruff: noqa: B008

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext

router = APIRouter(
    prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)]
)


@router.get("/stats")
async def stats(context: ServiceContext = Depends(get_context)) -> dict[str, object]:
    """Return lightweight persisted source and schedule counts for the dashboard."""
    if context.db is None or context.scheduler is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    row = await context.db.fetchone("SELECT COUNT(*) AS count FROM source_data")
    return {
        "source_count": int(row["count"]) if row is not None else 0,
        "scheduled_tasks": len(context.scheduler._tasks),
    }


@router.get("/logs")
async def logs(
    limit: int = Query(default=20, ge=1, le=100), context: ServiceContext = Depends(get_context)
) -> list[dict[str, object]]:
    """Return recent task log rows with bounded pagination."""
    if context.db is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    rows = await context.db.fetchall("SELECT * FROM task_logs ORDER BY id DESC LIMIT ?", (limit,))
    return [dict(cast(Mapping[str, object], row)) for row in rows]


@router.post("/ingest")
async def ingest(
    payload: dict[str, object], context: ServiceContext = Depends(get_context)
) -> dict[str, object]:
    """Trigger a configured adapter or a provided adapter configuration batch."""
    if context.ingestion is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    adapter_id = payload.get("adapter_id")
    if isinstance(adapter_id, str):
        config = payload.get("config", {})
        if not isinstance(config, Mapping):
            raise HTTPException(status_code=400, detail="config must be an object")
        count = await context.ingestion.run_single(adapter_id, dict(config))
        return {"result_count": count}
    configs = payload.get("adapter_configs", [])
    if not isinstance(configs, list) or not all(isinstance(item, dict) for item in configs):
        raise HTTPException(status_code=400, detail="adapter_id or adapter_configs is required")
    return {"results": await context.ingestion.run_all(configs)}
