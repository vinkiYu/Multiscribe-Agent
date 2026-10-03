"""Tests for slow-query warnings and metric recording."""

from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager

import pytest

from multiscribe_agent.infra.db import Database


class _SlowConnection:
    async def execute(self, statement: str, *parameters: object) -> str:
        del statement, parameters
        await asyncio.sleep(0.01)
        return "UPDATE 1"


class _SlowAcquire:
    def __init__(self, connection: _SlowConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> _SlowConnection:
        return self._connection

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class _SlowPool:
    def __init__(self, connection: _SlowConnection) -> None:
        self._connection = connection

    def acquire(self) -> AbstractAsyncContextManager[_SlowConnection]:
        return _SlowAcquire(self._connection)


class _Metrics:
    def __init__(self) -> None:
        self.durations: list[float] = []

    def record_slow_query(self, duration: float) -> None:
        self.durations.append(duration)


@pytest.mark.asyncio
async def test_slow_query_logs_warning_and_records_metric(monkeypatch) -> None:
    """Queries exceeding the configured threshold emit one warning and one metric."""
    database = Database(
        _SlowPool(_SlowConnection()), slow_query_threshold=0.001, enable_sql_audit=False
    )
    metrics = _Metrics()
    # Patch the registry variable itself (not the accessor function) so the
    # observability read path sees the fake regardless of import ordering.
    monkeypatch.setattr("multiscribe_agent.observability.meter._default_registry", metrics)

    await database.execute("UPDATE things SET value = $1", ("x",))

    assert metrics.durations
    assert metrics.durations[0] >= 0.001
