"""Stored agent CRUD and SSE harness execution endpoints."""
# ruff: noqa: B008

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.domain.models import AgentDefinition

router = APIRouter(prefix="/api/agents", tags=["agents"], dependencies=[Depends(get_current_user)])


@router.get("")
async def list_agents(context: ServiceContext = Depends(get_context)) -> list[dict[str, object]]:
    """List persisted agent declarations."""
    if context.entities is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    return await context.entities.list_all("agents")


@router.post("")
async def save_agent(
    payload: dict[str, object], context: ServiceContext = Depends(get_context)
) -> dict[str, object]:
    """Validate and persist one agent declaration."""
    if context.entities is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    agent = AgentDefinition.model_validate(payload)
    data = agent.model_dump(mode="json")
    await context.entities.save("agents", agent.id, data)
    return data


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str, context: ServiceContext = Depends(get_context)
) -> dict[str, str]:
    """Delete one stored agent declaration."""
    if context.entities is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    await context.entities.delete("agents", agent_id)
    return {"status": "deleted"}


@router.post("/{agent_id}/run")
async def run_agent(
    agent_id: str, payload: dict[str, object], context: ServiceContext = Depends(get_context)
) -> EventSourceResponse:
    """Stream P4 harness events as SSE."""
    if context.entities is None or context.agent_executor is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    raw = await context.entities.get("agents", agent_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="agent not found")
    user_input = payload.get("input", "")
    if not isinstance(user_input, str):
        raise HTTPException(status_code=400, detail="input must be a string")

    executor = context.agent_executor

    async def events() -> AsyncIterator[dict[str, str]]:
        async for event in executor.stream(AgentDefinition.model_validate(raw), user_input):
            yield {"event": event.type, "data": json.dumps(event.data)}

    return EventSourceResponse(events())
