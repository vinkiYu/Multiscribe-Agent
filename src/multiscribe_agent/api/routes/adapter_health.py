"""Authenticated adapter-health inspection and manual recovery endpoints."""
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.core.adapter_health import AdapterHealthRepository
from multiscribe_agent.infra.db import Database

router = APIRouter(
    prefix="/api/adapter-health",
    tags=["adapter-health"],
    dependencies=[Depends(get_current_user)],
)


def _services(context: ServiceContext) -> tuple[AdapterHealthRepository, Database]:
    """Resolve the health repository and initialized database for one request."""
    if context.adapter_health_repo is None or context.db is None:
        raise HTTPException(status_code=503, detail="services unavailable")
    return context.adapter_health_repo, context.db


@router.get("")
async def list_adapter_health(
    context: ServiceContext = Depends(get_context),
) -> list[dict[str, object]]:
    """List persisted health state for adapters that have run."""
    repository, database = _services(context)
    health = await repository.list_all(database)
    return [item.to_dict() for item in health]


@router.post("/{adapter_id}/enable")
async def enable_adapter(
    adapter_id: str,
    context: ServiceContext = Depends(get_context),
) -> dict[str, object]:
    """Clear an adapter failure streak and allow it to run again."""
    repository, database = _services(context)
    await repository.set_disabled(database, adapter_id=adapter_id, disabled=False)
    health = await repository.get(database, adapter_id=adapter_id)
    if health is None:
        raise HTTPException(status_code=404, detail="adapter health not found")
    return health.to_dict()


@router.post("/{adapter_id}/disable")
async def disable_adapter(
    adapter_id: str,
    context: ServiceContext = Depends(get_context),
) -> dict[str, object]:
    """Manually disable an adapter until an operator enables it."""
    repository, database = _services(context)
    await repository.set_disabled(database, adapter_id=adapter_id, disabled=True)
    health = await repository.get(database, adapter_id=adapter_id)
    if health is None:
        raise HTTPException(status_code=404, detail="adapter health not found")
    return health.to_dict()
