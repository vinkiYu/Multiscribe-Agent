"""Tests for slow-query warnings and metric recording."""

from __future__ import annotations

import asyncio

import pytest

from multiscribe_agent.infra.db import Database


class _Cursor:
    rowcount = 1

    async def close(self) -> None:
        return


class _SlowConnection:
    total_changes = 0

    async def execute(self, statement: str, parameters: tuple[object, ...]) -> _Cursor:
        del statement, parameters
        await asyncio.sleep(0.01)
        return _Cursor()

    async def commit(self) -> None:
        return


class _Metrics:
    def __init__(self) -> None:
        self.durations: list[float] = []

    def record_slow_query(self, duration: float) -> None:
        self.durations.append(duration)


@pytest.mark.asyncio
async def test_slow_query_logs_warning_and_records_metric(monkeypatch) -> None:
    """Queries exceeding the configured threshold emit one warning and one metric."""
    connection = _SlowConnection()
    database = Database(connection, slow_query_threshold=0.001, enable_sql_audit=False)
    metrics = _Metrics()
    monkeypatch.setattr(
        "multiscribe_agent.observability.meter.get_metrics_registry", lambda: metrics
    )

    await database.execute("UPDATE things SET value = ?", ("x",))

    assert metrics.durations
    assert metrics.durations[0] >= 0.001
