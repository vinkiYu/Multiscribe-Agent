"""Schedule CRUD and immediate scheduler trigger endpoints."""
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.domain.models import ScheduleTask

router = APIRouter(
    prefix="/api/schedules", tags=["schedules"], dependencies=[Depends(get_current_user)]
)


@router.get("")
async def list_schedules(context: ServiceContext = Depends(get_context)) -> list[dict[str, object]]:
    """List persisted schedule definitions."""
    if context.entities is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    return await context.entities.list_all("schedules")


@router.post("")
async def save_schedule(
    payload: dict[str, object], context: ServiceContext = Depends(get_context)
) -> dict[str, object]:
    """Validate, persist, and register one scheduled callback when available."""
    if context.entities is None or context.scheduler is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    task = ScheduleTask.model_validate(payload)
    await context.entities.save("schedules", task.id, task.model_dump(mode="json"))
    callback = context.scheduler._registry.get(task.task_type)
    if task.enabled and callback is not None:
        context.scheduler.register(task, callback)
    return task.model_dump(mode="json")


@router.delete("/{task_id}")
async def delete_schedule(
    task_id: str, context: ServiceContext = Depends(get_context)
) -> dict[str, str]:
    """Delete persisted data and unregister the future cron job."""
    if context.entities is None or context.scheduler is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    context.scheduler.unregister(task_id)
    await context.entities.delete("schedules", task_id)
    return {"status": "deleted"}


@router.post("/{task_id}/run")
async def run_schedule(
    task_id: str, context: ServiceContext = Depends(get_context)
) -> dict[str, str]:
    """Invoke one registered schedule immediately."""
    if context.scheduler is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    await context.scheduler.run_now(task_id)
    return {"status": "started"}
