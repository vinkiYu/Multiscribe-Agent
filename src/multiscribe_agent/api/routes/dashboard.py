"""Dashboard statistics, recent logs, and manual ingestion endpoints."""
# ruff: noqa: B008

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
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


@router.get("/overview")
async def overview(context: ServiceContext = Depends(get_context)) -> dict[str, object]:
    """Return the single payload consumed by the operations dashboard."""
    if context.db is None or context.daily_usage is None or context.publish_history is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    usage_rows = await context.daily_usage.query(today, today)
    usage = usage_rows[0] if usage_rows else None
    from_date = datetime.strptime(today, "%Y-%m-%d").replace(tzinfo=UTC)
    publish = await context.publish_history.summary(context.db, from_date, datetime.now(UTC))
    iterations: list[dict[str, object]] = []
    if context.iteration_store is not None:
        iterations = [
            {
                "workflow_run_id": item.workflow_run_id,
                "step_id": item.step_id,
                "round": item.round,
                "score": item.score,
                "converged": item.converged,
                "reason": item.reason,
            }
            for item in await context.iteration_store.list_recent(limit=20)
        ]
    rows = await context.db.fetchall("SELECT * FROM task_logs ORDER BY id DESC LIMIT 20")
    return {
        "usage": {
            "date": usage.date if usage else today,
            "input_tokens": usage.input_tokens if usage else 0,
            "output_tokens": usage.output_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
            "llm_calls": usage.llm_calls if usage else 0,
            "task_count": usage.task_count if usage else 0,
        },
        "publish": publish,
        "iterations": iterations,
        "task_logs": [dict(cast(Mapping[str, object], row)) for row in rows],
    }


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
