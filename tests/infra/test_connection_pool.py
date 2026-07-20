"""Tests for concurrent read lanes and serialized SQLite writes."""

from __future__ import annotations

import asyncio

import pytest

from multiscribe_agent.infra.connection_pool import ConnectionPool


@pytest.mark.asyncio
async def test_pool_supports_concurrent_reads_and_one_writer(tmp_path) -> None:
    """Readers share N connections while writes hold one exclusive lane."""
    path = tmp_path / "pool.sqlite"
    pool = ConnectionPool(str(path), read_pool_size=3)
    await pool.initialize()
    try:
        async with pool.acquire_write() as writer:
            await writer.execute("CREATE TABLE values_table(value INTEGER)")
            await writer.commit()
            await writer.execute("INSERT INTO values_table(value) VALUES (1)")
            await writer.commit()

        async def read_value() -> int:
            async with pool.acquire_read() as reader:
                cursor = await reader.execute("SELECT value FROM values_table")
                row = await cursor.fetchone()
                await cursor.close()
                return int(row[0])

        assert await asyncio.gather(*(read_value() for _ in range(6))) == [1] * 6

        active = 0
        maximum = 0
        guard = asyncio.Lock()

        async def write_value(value: int) -> None:
            nonlocal active, maximum
            async with pool.acquire_write() as writer:
                async with guard:
                    active += 1
                    maximum = max(maximum, active)
                await asyncio.sleep(0)
                await writer.execute("INSERT INTO values_table(value) VALUES (?)", (value,))
                await writer.commit()
                async with guard:
                    active -= 1

        await asyncio.gather(write_value(2), write_value(3))
        assert maximum == 1
        assert pool.stats.acquires >= 9
    finally:
        await pool.close()
