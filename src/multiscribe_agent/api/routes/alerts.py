"""Authenticated alert history API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.core.alert_history import AlertRecord

router = APIRouter(
    prefix="/api/alerts",
    tags=["alerts"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
async def list_alerts(
    limit: int = Query(default=50, ge=1, le=200),
    acknowledged: bool | None = Query(default=None),
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> list[dict[str, object]]:
    """Return newest alert history rows for the operations console."""
    if context.alert_history is None:
        raise HTTPException(status_code=503, detail="alerts unavailable")
    records = await context.alert_history.query_recent(
        limit=limit,
        acknowledged=acknowledged,
    )
    return [_record_to_response(record) for record in records]


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Mark one alert as acknowledged and return the updated record."""
    if not alert_id.strip():
        raise HTTPException(status_code=400, detail="alert_id must not be empty")
    if context.alert_history is None:
        raise HTTPException(status_code=503, detail="alerts unavailable")
    await context.alert_history.acknowledge(alert_id, by="operator")
    records = await context.alert_history.query_recent(limit=200)
    record = next((item for item in records if item.id == alert_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="alert not found")
    if not record.acknowledged:
        raise HTTPException(
            status_code=500,
            detail="alert acknowledged flag not persisted; check server logs",
        )
    return _record_to_response(record)


def _record_to_response(record: AlertRecord) -> dict[str, object]:
    """Serialize an alert record without exposing internal repository state."""
    return {
        "id": record.id,
        "rule_name": record.rule_name,
        "metric": record.metric,
        "threshold": record.threshold,
        "value": record.value,
        "description": record.description,
        "fired_at": record.fired_at,
        "acknowledged": record.acknowledged,
        "acknowledged_by": record.acknowledged_by,
        "acknowledged_at": record.acknowledged_at,
        "metadata": record.metadata,
    }
