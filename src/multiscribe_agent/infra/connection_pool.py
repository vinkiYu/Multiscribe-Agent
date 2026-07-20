"""SQLite WAL-aware pool with concurrent read lanes and one serialized writer."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import aiosqlite


@dataclass(slots=True)
class PoolStats:
    """Basic pool contention counters for diagnostics and tests."""

    acquires: int = 0
    releases: int = 0
    read_waits: int = 0
    write_waits: int = 0


class ConnectionPool:
    """Bounded read pool plus one exclusive write connection."""

    def __init__(
        self,
        db_path: str,
        *,
        read_pool_size: int = 5,
        write_timeout: float = 30.0,
    ) -> None:
        if read_pool_size <= 0:
            raise ValueError("read_pool_size must be positive")
        if write_timeout <= 0:
            raise ValueError("write_timeout must be positive")
        self._db_path = db_path
        self._read_pool_size = read_pool_size
        self._write_timeout = write_timeout
        self._read_sem = asyncio.Semaphore(read_pool_size)
        self._write_lock = asyncio.Lock()
        self._read_connections: list[aiosqlite.Connection] = []
        self._write_connection: aiosqlite.Connection | None = None
        self._initialized = False
        self.stats = PoolStats()

    @property
    def write_connection(self) -> aiosqlite.Connection:
        """Return the initialized writer connection for schema operations."""
        if self._write_connection is None:
            raise RuntimeError("connection pool is not initialized")
        return self._write_connection

    async def initialize(self) -> None:
        """Open all lanes once and configure SQLite WAL settings."""
        if self._initialized:
            return
        if self._db_path == ":memory:":
            raise ValueError("ConnectionPool requires a file-backed SQLite database")
        try:
            for _ in range(self._read_pool_size):
                connection = await self._open_connection()
                await connection.execute("PRAGMA query_only = ON")
                await connection.commit()
                self._read_connections.append(connection)
            self._write_connection = await self._open_connection()
            await self._write_connection.execute("PRAGMA query_only = OFF")
            await self._write_connection.commit()
            self._initialized = True
        except BaseException:
            await self.close()
            raise

    async def _open_connection(self) -> aiosqlite.Connection:
        connection = await aiosqlite.connect(self._db_path)
        connection.row_factory = aiosqlite.Row
        for statement in (
            "PRAGMA journal_mode=WAL",
            "PRAGMA busy_timeout=5000",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA foreign_keys=ON",
        ):
            cursor = await connection.execute(statement)
            await cursor.close()
        await connection.commit()
        return connection

    @asynccontextmanager
    async def acquire_read(self) -> AsyncIterator[aiosqlite.Connection]:
        """Acquire a read connection; readers run concurrently up to pool size."""
        if self._read_sem.locked():
            self.stats.read_waits += 1
        await self._read_sem.acquire()
        self.stats.acquires += 1
        connection = self._read_connections.pop()
        try:
            yield connection
        finally:
            self._read_connections.append(connection)
            self.stats.releases += 1
            self._read_sem.release()

    @asynccontextmanager
    async def acquire_write(self) -> AsyncIterator[aiosqlite.Connection]:
        """Acquire the single writer connection and serialize writes."""
        if self._write_lock.locked():
            self.stats.write_waits += 1
        try:
            await asyncio.wait_for(self._write_lock.acquire(), timeout=self._write_timeout)
        except TimeoutError:
            raise TimeoutError("timed out waiting for SQLite write connection") from None
        self.stats.acquires += 1
        try:
            yield self.write_connection
        finally:
            self.stats.releases += 1
            self._write_lock.release()

    async def close(self) -> None:
        """Close every pool connection and reset initialization state."""
        for connection in self._read_connections:
            await connection.close()
        self._read_connections.clear()
        if self._write_connection is not None:
            await self._write_connection.close()
            self._write_connection = None
        self._initialized = False
