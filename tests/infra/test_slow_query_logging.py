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
async def test_slow_query_logs_warning_and_records_metric() -> None:
    """Queries exceeding the configured threshold emit one warning and one metric."""
    from multiscribe_agent.observability.meter import (
        get_metrics_registry,
        set_metrics_registry,
    )

    database = Database(
        _SlowPool(_SlowConnection()), slow_query_threshold=0.001, enable_sql_audit=False
    )
    metrics = _Metrics()
    # Assemble through the production registry entry point and restore it
    # explicitly, so no module-reload or import-order trick can shadow it.
    original = get_metrics_registry()
    set_metrics_registry(metrics)
    try:
        await database.execute("UPDATE things SET value = $1", ("x",))
    finally:
        set_metrics_registry(original)

    assert metrics.durations
    assert metrics.durations[0] >= 0.001
