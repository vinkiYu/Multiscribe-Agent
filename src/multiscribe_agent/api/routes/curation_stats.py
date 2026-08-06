"""Authenticated daily curation quality statistics for the operations console."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
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
    ci_baseline: float | None = None


class CurationBaselineResponse(BaseModel):
    """Optional offline F1 baseline displayed beside production trend data."""

    avg_f1: float | None


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
    baseline = _read_ci_baseline()
    return [
        DailyCurationStatResponse.model_validate(record).model_copy(
            update={"ci_baseline": baseline}
        )
        for record in records
    ]


@router.get("/baseline", response_model=CurationBaselineResponse)
async def get_curation_baseline() -> CurationBaselineResponse:
    """Return the checked-in baseline, or null before the first labelled run."""
    return CurationBaselineResponse(avg_f1=_read_ci_baseline())


def _read_ci_baseline() -> float | None:
    """Read the checked-in curation F1 baseline without making the API depend on it."""
    candidates = (
        Path.cwd() / "data" / "eval" / "baselines" / "curation_recall.json",
        Path(__file__).resolve().parents[4]
        / "data"
        / "eval"
        / "baselines"
        / "curation_recall.json",
    )
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        value = payload.get("avg_f1") if isinstance(payload, dict) else None
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return None
