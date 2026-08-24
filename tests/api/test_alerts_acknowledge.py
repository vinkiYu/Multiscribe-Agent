"""HTTP coverage for the authenticated alerts acknowledge endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.api.conftest import auth_headers


async def _seed_alert(context: object, *, record_id: str) -> None:
    """Insert a single alert row into the in-memory alert history."""
    assert context.alert_history is not None
    await context.alert_history.record(
        rule_name="adapter_error_rate",
        metric="error_rate",
        threshold=0.5,
        value=0.9,
        description="synthetic alert for acknowledge coverage",
        fired_at=1_700_000_000,
        metadata={"source": "test"},
    )

    # Promote the synthetic record to a known id so the route can address it.
    async def _rename() -> None:
        await context.alert_history._execute(
            "UPDATE alert_history SET id = ? WHERE id = ("
            "SELECT id FROM alert_history ORDER BY fired_at DESC LIMIT 1"
            ")",
            (record_id,),
        )

    await _rename()


@pytest.mark.asyncio
async def test_acknowledge_alert_marks_record_acknowledged(client: AsyncClient) -> None:
    """A 200 response flips acknowledged=True and stamps acknowledged_by='operator'."""
    context = client._transport.app.state.context  # type: ignore[attr-defined]
    await _seed_alert(context, record_id="ack-target")

    headers = await auth_headers(client)
    response = await client.post("/api/alerts/ack-target/acknowledge", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "ack-target"
    assert body["acknowledged"] is True
    assert body["acknowledged_by"] == "operator"
    assert body["acknowledged_at"] is not None


@pytest.mark.asyncio
async def test_acknowledge_alert_returns_404_for_unknown_id(client: AsyncClient) -> None:
    """An unknown alert id is rejected with 404 after the acknowledge write."""
    headers = await auth_headers(client)
    response = await client.post("/api/alerts/never-existed/acknowledge", headers=headers)
    assert response.status_code == 404
    assert "alert not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_acknowledge_alert_rejects_blank_id(client: AsyncClient) -> None:
    """A blank id is rejected with 400 before any persistence work."""
    headers = await auth_headers(client)
    response = await client.post("/api/alerts/%20/acknowledge", headers=headers)
    assert response.status_code == 400
    assert "alert_id" in response.json()["detail"]
