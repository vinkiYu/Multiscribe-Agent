"""Authenticated read access to persisted Workflow Loop iterations."""
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from multiscribe_agent.agents.workflow.iteration_store import IterationRecord, IterationStore
from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext

router = APIRouter(
    prefix="/api/workflow-iterations",
    tags=["workflow-iterations"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
async def list_workflow_iterations(
    run_id: str | None = Query(default=None),
    step_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    context: ServiceContext = Depends(get_context),
) -> list[dict[str, object]]:
    """Return one Loop step's history or the latest records across all runs."""
    if (run_id is None) != (step_id is None):
        raise HTTPException(status_code=400, detail="run_id and step_id must be provided together")
    if context.db is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    store = context.iteration_store or IterationStore(context.db)
    if run_id is not None and step_id is not None:
        records = await store.list_for_step(run_id, step_id)
        return _serialize_step_records(records)
    records = await store.list_recent(limit)
    return [_serialize_record(record) for record in records]


def _serialize_step_records(records: list[IterationRecord]) -> list[dict[str, object]]:
    """Add score deltas for records belonging to one run and step."""
    previous_score: float | None = None
    payload: list[dict[str, object]] = []
    for record in records:
        delta = (
            abs(record.score - previous_score)
            if record.score is not None and previous_score is not None
            else None
        )
        payload.append(_serialize_record(record, delta=delta))
        if record.score is not None:
            previous_score = record.score
    return payload


def _serialize_record(record: IterationRecord, *, delta: float | None = None) -> dict[str, object]:
    """Serialize the stable, dashboard-facing iteration contract."""
    return {
        "workflow_run_id": record.workflow_run_id,
        "step_id": record.step_id,
        "round": record.round,
        "output": record.output,
        "score": record.score,
        "delta": delta,
        "feedback": record.feedback,
        "converged": record.converged,
        "reason": record.reason,
    }
