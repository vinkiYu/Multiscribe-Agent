"""Authenticated read APIs for daily-digest curation quality observations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.infra.repositories.curation_evaluations import CurationEvaluationRecord

router = APIRouter(
    prefix="/api/curation-evaluations",
    tags=["curation-evaluations"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/summary")
async def summary(
    from_date: str | None = None,
    to_date: str | None = None,
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Return curation quality aggregates for an inclusive optional date window."""
    if context.curation_evaluations is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    return await context.curation_evaluations.summary(from_date, to_date)


@router.get("")
async def list_evaluations(
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> list[dict[str, object]]:
    """Return newest persisted curation evaluation rows for authorized callers."""
    if context.curation_evaluations is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    records = await context.curation_evaluations.query(from_date, to_date, limit)
    return [_record_to_response(record) for record in records]


def _record_to_response(record: CurationEvaluationRecord) -> dict[str, object]:
    """Serialize the typed persistence boundary for the public read API."""
    return {
        "workflow_run_id": record.workflow_run_id,
        "date": record.date,
        "recorded_at": record.recorded_at,
        "rounds": record.rounds,
        "converged": record.converged,
        "exit_reason": record.exit_reason,
        "final_score": record.final_score,
        "score_delta": record.score_delta,
        "avg_iter_score": record.avg_iter_score,
        "result_count": record.result_count,
        "usage": record.usage,
    }
