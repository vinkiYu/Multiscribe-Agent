"""Stored workflow CRUD and SSE execution endpoints."""
# ruff: noqa: B008

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.domain.models import WorkflowDefinition

router = APIRouter(
    prefix="/api/workflows", tags=["workflows"], dependencies=[Depends(get_current_user)]
)


@router.get("")
async def list_workflows(context: ServiceContext = Depends(get_context)) -> list[dict[str, object]]:
    """List persisted workflow definitions."""
    if context.entities is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    return await context.entities.list_all("workflows")


@router.post("")
async def save_workflow(
    payload: dict[str, object], context: ServiceContext = Depends(get_context)
) -> dict[str, object]:
    """Validate and persist one workflow definition."""
    if context.entities is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    workflow = WorkflowDefinition.model_validate(payload)
    data = workflow.model_dump(mode="json")
    await context.entities.save("workflows", workflow.id, data)
    return data


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str, context: ServiceContext = Depends(get_context)
) -> dict[str, str]:
    """Delete one workflow definition."""
    if context.entities is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    await context.entities.delete("workflows", workflow_id)
    return {"status": "deleted"}


@router.post("/{workflow_id}/run")
async def run_workflow(
    workflow_id: str, payload: dict[str, object], context: ServiceContext = Depends(get_context)
) -> EventSourceResponse:
    """Stream P10 workflow events as SSE."""
    if context.workflow_engine is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    value = payload.get("input", "")

    engine = context.workflow_engine

    async def events() -> AsyncIterator[dict[str, str]]:
        async for event in engine.stream(workflow_id, value):
            yield {"event": event.type, "data": json.dumps(event.data)}

    return EventSourceResponse(events())
