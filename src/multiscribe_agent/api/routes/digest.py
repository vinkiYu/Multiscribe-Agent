"""Manual daily-digest pipeline trigger."""
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.domain.models import ScheduleTask

router = APIRouter(prefix="/api/digest", tags=["digest"], dependencies=[Depends(get_current_user)])


@router.post("/run")
async def run_digest(
    payload: dict[str, object], context: ServiceContext = Depends(get_context)
) -> dict[str, object]:
    """Execute P11 immediately using an API-provided daily-digest configuration."""
    task = ScheduleTask(
        id="manual-daily-digest",
        name="Manual daily digest",
        task_type="daily_digest",
        cron="0 0 * * *",
        config=payload,
    )
    try:
        return await context.run_daily_digest_task(task)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
