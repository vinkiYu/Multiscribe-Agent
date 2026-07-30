"""Tests for durable alert history persistence and acknowledgement filters."""

from __future__ import annotations

import pytest

from multiscribe_agent.core.alert_history import AlertHistoryRepository
from multiscribe_agent.infra.db import init_db


@pytest.mark.asyncio
async def test_alert_history_records_queries_and_acknowledges() -> None:
    db = await init_db(":memory:")
    try:
        repository = AlertHistoryRepository(db)
        first_id = await repository.record(
            rule_name="latency",
            metric="llm_latency",
            threshold=2.0,
            value=3.5,
            description="slow model call",
            fired_at=100,
            metadata={"source": "test"},
        )
        assert len(first_id) == 26
        second_id = await repository.record(
            rule_name="errors",
            metric="error_count",
            threshold=1.0,
            value=2.0,
            description="errors increased",
            fired_at=200,
        )

        recent = await repository.query_recent()
        assert [record.id for record in recent] == [second_id, first_id]
        assert recent[1].metadata == {"source": "test"}
        assert recent[0].acknowledged is False

        await repository.acknowledge(first_id, "operator")
        acknowledged = await repository.query_recent(acknowledged=True)
        pending = await repository.query_recent(acknowledged=False)
        assert [record.id for record in acknowledged] == [first_id]
        assert [record.id for record in pending] == [second_id]
        assert acknowledged[0].acknowledged_by == "operator"
        assert acknowledged[0].acknowledged_at is not None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_alert_history_query_limit_is_bounded() -> None:
    db = await init_db(":memory:")
    try:
        repository = AlertHistoryRepository(db)
        for index in range(3):
            await repository.record(
                rule_name="test",
                metric="metric",
                threshold=0.0,
                value=float(index),
                description="",
                fired_at=index,
            )
        assert len(await repository.query_recent(limit=1)) == 1
        assert len(await repository.query_recent(limit=0)) == 1
        assert len(await repository.query_recent(limit=999)) == 3
    finally:
        await db.close()
