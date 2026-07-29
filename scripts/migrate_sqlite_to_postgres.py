"""Migrate SQLite rows to PostgreSQL in bounded batches with verification.

The command moves data only. PostgreSQL extensions and Phase 3 search tables are
initialized through the existing schema constants, while business-table schema
ownership remains with the normal database migration path.

Examples:
    python -m scripts.migrate_sqlite_to_postgres --dry-run
    python -m scripts.migrate_sqlite_to_postgres \
        --sqlite-path data/database.sqlite \
        --pg-dsn postgresql://postgres:password@localhost:5432/multiscribe
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

import aiosqlite
import structlog

log = structlog.get_logger(__name__)

MIGRATION_ORDER: tuple[str, ...] = (
    "kv",
    "agents",
    "skills",
    "workflows",
    "mcp_configs",
    "schedules",
    "source_data",
    "task_logs",
    "workflow_iterations",
    "daily_usage",
    "publish_history",
    "click_events",
    "pushed_content",
    "memory_categories",
    "agent_memories",
    "kb_categories",
    "kb_documents",
    "kb_chunks",
    "commit_history",
    "sql_audit_log",
    "api_keys",
    "interop_keys",
    "embeddings",
    "curation_evaluations",
    "daily_digest_archives",
)

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class _PgConnection(Protocol):
    """Subset of an asyncpg connection used by the migration."""

    async def execute(self, statement: str, *parameters: object) -> str:
        """Execute one statement."""

    async def executemany(self, statement: str, parameter_sets: Sequence[Sequence[object]]) -> None:
        """Execute one statement for a batch of rows."""

    async def fetchval(self, statement: str, *parameters: object) -> object:
        """Fetch one scalar value."""


class _PgPool(Protocol):
    """Subset of an asyncpg pool used by the migration."""

    def acquire(self) -> AbstractAsyncContextManager[_PgConnection]:
        """Acquire one PostgreSQL connection."""

    async def close(self) -> None:
        """Close the pool."""


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """Result for one migrated or skipped table."""

    table: str
    source_count: int
    migrated_rows: int
    status: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DriftReport:
    """Source and target row-count comparison for one table."""

    table: str
    source_count: int
    target_count: int | None
    drift: int | None
    status: str


async def migrate_table(
    sqlite_conn: aiosqlite.Connection,
    pg_pool: _PgPool | None,
    table: str,
    columns: list[str] | None = None,
    batch_size: int = 500,
    *,
    dry_run: bool = False,
) -> MigrationResult:
    """Copy one SQLite table to PostgreSQL in bounded batches.

    Missing source tables are reported as ``skipped``. Dry-run mode reads only
    SQLite metadata and row counts and never acquires a PostgreSQL connection.
    """
    _validate_identifier(table)
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if not await _table_exists(sqlite_conn, table):
        return MigrationResult(table, 0, 0, "skipped")

    source_count = await _sqlite_count(sqlite_conn, table)
    selected_columns = columns or await _table_columns(sqlite_conn, table)
    if dry_run:
        return MigrationResult(table, source_count, 0, "dry-run")
    if pg_pool is None:
        raise ValueError("pg_pool is required when dry_run is false")
    if not selected_columns:
        return MigrationResult(table, source_count, 0, "skipped", "table has no columns")

    placeholders = ", ".join(f"${index}" for index in range(1, len(selected_columns) + 1))
    quoted_columns = ", ".join(_quote_identifier(column) for column in selected_columns)
    insert_sql = (
        f"INSERT INTO {_quote_identifier(table)} ({quoted_columns}) "  # noqa: S608
        f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
    )
    select_sql = f"SELECT {quoted_columns} FROM {_quote_identifier(table)}"  # noqa: S608
    cursor = await sqlite_conn.execute(select_sql)
    migrated_rows = 0
    while True:
        rows = await cursor.fetchmany(batch_size)
        if not rows:
            break
        values = [tuple(row[column] for column in selected_columns) for row in rows]
        async with pg_pool.acquire() as connection:
            await connection.executemany(insert_sql, values)
        migrated_rows += len(values)
    await cursor.close()
    return MigrationResult(table, source_count, migrated_rows, "migrated")


async def verify_row_counts(
    sqlite_conn: aiosqlite.Connection,
    pg_pool: _PgPool,
    tables: Sequence[str] = MIGRATION_ORDER,
) -> list[DriftReport]:
    """Compare row counts after migration without copying or mutating data."""
    reports: list[DriftReport] = []
    for table in tables:
        _validate_identifier(table)
        if not await _table_exists(sqlite_conn, table):
            continue
        source_count = await _sqlite_count(sqlite_conn, table)
        try:
            async with pg_pool.acquire() as connection:
                value = await connection.fetchval(
                    f"SELECT COUNT(*) FROM {_quote_identifier(table)}"  # noqa: S608
                )
            target_count = int(value or 0)
        except Exception as exc:
            log.warning("migration_row_count_failed", table=table, error=str(exc))
            reports.append(DriftReport(table, source_count, None, None, "error"))
            continue
        drift = source_count - target_count
        reports.append(
            DriftReport(
                table,
                source_count,
                target_count,
                drift,
                "match" if drift == 0 else "drift",
            )
        )
    return reports


async def run_migration(
    sqlite_path: Path,
    pg_dsn: str,
    *,
    batch_size: int = 500,
    dry_run: bool = False,
    report_dir: Path = Path("logs"),
    tables: Sequence[str] = MIGRATION_ORDER,
) -> dict[str, object]:
    """Run the migration and write a JSON report, preserving the SQLite source."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if not dry_run and not pg_dsn.strip():
        raise ValueError("--pg-dsn is required unless --dry-run is used")

    sqlite_conn = await aiosqlite.connect(sqlite_path)
    sqlite_conn.row_factory = aiosqlite.Row
    pg_pool: _PgPool | None = None
    results: list[MigrationResult] = []
    drift: list[DriftReport] = []
    try:
        if not dry_run:
            pg_pool = await _open_pg_pool(pg_dsn)
            await _apply_search_schema(pg_pool)
        for table in tables:
            try:
                results.append(
                    await migrate_table(
                        sqlite_conn,
                        pg_pool,
                        table,
                        batch_size=batch_size,
                        dry_run=dry_run,
                    )
                )
            except Exception as exc:
                source_count = (
                    await _sqlite_count(sqlite_conn, table)
                    if await _table_exists(sqlite_conn, table)
                    else 0
                )
                log.error("migration_table_failed", table=table, error=str(exc))
                results.append(MigrationResult(table, source_count, 0, "error", str(exc)))
        if pg_pool is not None:
            drift = await verify_row_counts(sqlite_conn, pg_pool, tables)
    finally:
        await sqlite_conn.close()
        if pg_pool is not None:
            await pg_pool.close()

    report: dict[str, object] = {
        "created_at": datetime.now(UTC).isoformat(),
        "sqlite_path": str(sqlite_path),
        "dry_run": dry_run,
        "batch_size": batch_size,
        "results": [asdict(result) for result in results],
        "drift": [asdict(item) for item in drift],
        "table_reports": _table_reports(results, drift),
    }
    _write_report(report, report_dir)
    return report


async def main(args: argparse.Namespace) -> None:
    """Execute the CLI arguments and print a compact report location."""
    report = await run_migration(
        Path(args.sqlite_path),
        args.pg_dsn,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        report_dir=Path(args.report_dir),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _build_parser() -> argparse.ArgumentParser:
    """Build the migration command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-path", default="data/database.sqlite")
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--report-dir", default="logs")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def cli() -> None:
    """Parse arguments and run the asynchronous migration command."""
    asyncio.run(main(_build_parser().parse_args()))


async def _open_pg_pool(pg_dsn: str) -> _PgPool:
    """Open an asyncpg pool lazily so dry-run does not require the extra."""
    try:
        module = importlib.import_module("asyncpg")
    except ImportError as exc:
        raise ImportError(
            "asyncpg is required for migration. Install it with: "
            "pip install 'multiscribe-agent[postgres]'"
        ) from exc
    create_pool = cast(Callable[..., Awaitable[_PgPool]], module.__dict__["create_pool"])
    pool = await create_pool(dsn=pg_dsn, min_size=1, max_size=5, command_timeout=30)
    return cast(_PgPool, pool)


async def _apply_search_schema(pg_pool: _PgPool) -> None:
    """Apply the Phase 3 PostgreSQL vector and FTS support objects."""
    from multiscribe_agent.infra.postgres.schema_fts import (
        AGENT_MEMORIES_FTS_INDEXES,
        AGENT_MEMORIES_FTS_TABLE,
        CHUNK_VECTORS_TABLE,
        KB_CHUNKS_FTS_INDEX,
        KB_CHUNKS_FTS_TABLE,
        PGVECTOR_EXTENSION,
        SOURCE_DATA_FTS_INDEXES,
        SOURCE_DATA_FTS_TABLE,
    )

    statements = [
        PGVECTOR_EXTENSION,
        CHUNK_VECTORS_TABLE,
        SOURCE_DATA_FTS_TABLE,
        *SOURCE_DATA_FTS_INDEXES,
        KB_CHUNKS_FTS_TABLE,
        KB_CHUNKS_FTS_INDEX,
        AGENT_MEMORIES_FTS_TABLE,
        *AGENT_MEMORIES_FTS_INDEXES,
    ]
    async with pg_pool.acquire() as connection:
        for statement in statements:
            await connection.execute(statement)


async def _table_exists(connection: aiosqlite.Connection, table: str) -> bool:
    """Return whether a SQLite table exists."""
    cursor = await connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    )
    row = await cursor.fetchone()
    await cursor.close()
    return row is not None


async def _sqlite_count(connection: aiosqlite.Connection, table: str) -> int:
    """Count rows in one validated SQLite table."""
    cursor = await connection.execute(
        f"SELECT COUNT(*) FROM {_quote_identifier(table)}"  # noqa: S608
    )
    row = await cursor.fetchone()
    await cursor.close()
    return int(row[0]) if row is not None else 0


async def _table_columns(connection: aiosqlite.Connection, table: str) -> list[str]:
    """Read SQLite column names in their declared order."""
    cursor = await connection.execute(f"PRAGMA table_info({_quote_identifier(table)})")
    rows = await cursor.fetchall()
    await cursor.close()
    return [str(row[1]) for row in rows]


def _write_report(report: dict[str, object], report_dir: Path) -> Path:
    """Persist one timestamped migration report without exposing credentials."""
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = report_dir / f"migration-{timestamp}.json"
    report["report_path"] = str(path)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _table_reports(
    results: Sequence[MigrationResult], drift: Sequence[DriftReport]
) -> list[dict[str, object]]:
    """Combine migration and verification data using operator-friendly names."""
    drift_by_table = {item.table: item for item in drift}
    reports: list[dict[str, object]] = []
    for result in results:
        verification = drift_by_table.get(result.table)
        reports.append(
            {
                "table": result.table,
                "src_count": result.source_count,
                "dst_count": verification.target_count if verification else None,
                "drift": verification.drift if verification else None,
                "status": verification.status if verification else result.status,
                "migrated_rows": result.migrated_rows,
                "error": result.error,
            }
        )
    return reports


def _validate_identifier(value: str) -> None:
    """Reject dynamic SQL identifiers that are not simple table/column names."""
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"unsafe SQL identifier: {value!r}")


def _quote_identifier(value: str) -> str:
    """Quote a validated SQL identifier for both supported database engines."""
    _validate_identifier(value)
    return f'"{value}"'


if __name__ == "__main__":
    cli()
