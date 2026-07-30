"""Tests for alert cooldown, persistence wiring, and callback isolation."""

from __future__ import annotations

import asyncio

import pytest

from multiscribe_agent.core.alert_history import AlertHistoryRepository
from multiscribe_agent.infra.db import init_db
from multiscribe_agent.observability.alerts import AlertEngine, AlertRule


@pytest.mark.asyncio
async def test_alert_engine_persists_once_during_rule_cooldown() -> None:
    db = await init_db(":memory:")
    try:
        repository = AlertHistoryRepository(db)
        engine = AlertEngine([AlertRule("latency", "llm_latency", "threshold", 1.0)])
        engine.attach_alert_history(repository)
        delivered: list[str] = []

        async def callback(name: str, payload: dict[str, object]) -> None:
            del payload
            delivered.append(name)

        engine.add_callback(callback)
        engine.record("llm_latency", 2.0)
        await asyncio.sleep(0)
        engine.record("llm_latency", 3.0)
        await asyncio.sleep(0)

        records = await repository.query_recent()
        assert len(records) == 1
        assert records[0].rule_name == "latency"
        assert records[0].value == 2.0
        assert delivered == ["latency"]
        assert engine._last_fired["latency"] > 0
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_alert_history_failure_does_not_block_callbacks() -> None:
    class BrokenHistory:
        async def record(self, **_: object) -> str:
            raise RuntimeError("database unavailable")

    engine = AlertEngine([AlertRule("errors", "error_count", "threshold", 0.0)])
    engine.attach_alert_history(BrokenHistory())  # type: ignore[arg-type]
    delivered: list[str] = []

    async def callback(name: str, payload: dict[str, object]) -> None:
        del payload
        delivered.append(name)

    engine.add_callback(callback)
    engine.record("error_count", 1.0)
    await asyncio.sleep(0)
    assert delivered == ["errors"]
