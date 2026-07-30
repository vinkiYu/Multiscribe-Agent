"""Authenticated daily curation quality statistics for the operations console."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.infra.repositories.curation_stats import CurationStatsRepository

router = APIRouter(
    prefix="/api/curation-stats",
    tags=["curation-stats"],
    dependencies=[Depends(get_current_user)],
)


class DailyCurationStatResponse(BaseModel):
    """Public shape of one daily curation quality data point."""

    date: str
    final_score: float | None
    result_count: int | None
    total_scanned: int | None
    efficiency: float | None
    converged: bool
    exit_reason: str
    rounds: int


@router.get("/by-period", response_model=list[DailyCurationStatResponse])
async def get_curation_stats_by_period(
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> list[DailyCurationStatResponse]:
    """Return joined evaluation/archive metrics for an inclusive date window."""
    if context.db is None:
        raise HTTPException(status_code=503, detail="services unavailable")

    end = to_date or date.today()
    start = from_date or (end - timedelta(days=29))
    if start > end:
        raise HTTPException(status_code=422, detail="from_date must be on or before to_date")

    records = await CurationStatsRepository(context.db).get_by_period(
        start.isoformat(), end.isoformat()
    )
    return [DailyCurationStatResponse.model_validate(record) for record in records]
