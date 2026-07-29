"""Phase 5 migration, dialect, and optional PostgreSQL integration coverage."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from multiscribe_agent.config import SystemSettings
from multiscribe_agent.domain import ports
from multiscribe_agent.infra.dialect import PgDialect, SqlDialect, dialect_for
from scripts import migrate_sqlite_to_postgres as migration


def test_ports_includes_new_repositories() -> None:
    """The domain boundary exposes all repositories identified by Phase 5."""
    expected = (
        "AdapterHealthRepository",
        "ClickEventRepository",
        "PushedContentRepository",
        "IterationStore",
        "MemoryEntryRepository",
        "MemoryCategoryRepository",
        "DailyUsageRepository",
        "CurationEvaluationRepository",
    )
    assert all(hasattr(ports, name) for name in expected)


def test_dialect_translation() -> None:
    """SQLite passes through while PostgreSQL translates only bind placeholders."""
    sqlite = SqlDialect()
    postgres = PgDialect()

    assert sqlite.translate("SELECT '?' AS literal, ?") == "SELECT '?' AS literal, ?"
    assert postgres.translate("SELECT '?' AS literal, ?") == "SELECT '?' AS literal, $1"
    assert (
        dialect_for(type("Sqlite", (), {"placeholder_style": "question_mark"})()).translate(
            "SELECT ?"
        )
        == "SELECT ?"
    )
    postgres_backend = type(
        "Postgres",
        (),
        {"placeholder_style": type("Style", (), {"value": "dollar"})()},
    )()
    assert dialect_for(postgres_backend).translate("SELECT ?") == "SELECT $1"


def test_migrate_script_cli_args() -> None:
    """The migration CLI exposes explicit source, target, batching, and dry-run flags."""
    parser = migration._build_parser()
    args = parser.parse_args(
        [
            "--sqlite-path",
            "source.sqlite",
            "--pg-dsn",
            "postgresql://localhost/db",
            "--batch-size",
            "25",
            "--report-dir",
            "reports",
            "--dry-run",
        ]
    )
    assert args.sqlite_path == "source.sqlite"
    assert args.pg_dsn == "postgresql://localhost/db"
    assert args.batch_size == 25
    assert args.report_dir == "reports"
    assert args.dry_run is True


@pytest.mark.asyncio
async def test_migrate_dry_run(tmp_path: Path) -> None:
    """Dry-run reports source rows without importing asyncpg or touching a target."""
    source = tmp_path / "source.sqlite"
    async with aiosqlite.connect(source) as connection:
        await connection.execute("CREATE TABLE agents (id TEXT PRIMARY KEY, data TEXT)")
        await connection.executemany(
            "INSERT INTO agents(id, data) VALUES (?, ?)", [("a", "one"), ("b", "two")]
        )
        await connection.commit()

    report = await migration.run_migration(
        source,
        "",
        dry_run=True,
        tables=("agents", "missing_table"),
        report_dir=tmp_path / "reports",
    )

    assert report["dry_run"] is True
    results = report["results"]
    assert isinstance(results, list)
    assert results[0]["table"] == "agents"
    assert results[0]["source_count"] == 2
    assert results[0]["status"] == "dry-run"
    assert results[1]["status"] == "skipped"
    assert list((tmp_path / "reports").glob("migration-*.json"))


def test_migration_guide_sections() -> None:
    """The operator guide documents upgrade, rollback, health, and scope boundaries."""
    guide = Path("docs/postgres-migration-guide.md").read_text(encoding="utf-8")
    for section in ("## Upgrade Path", "## Rollback Path", "## Health Checks", "## Scope Boundary"):
        assert section in guide


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_postgres_end_to_end_pipeline(postgres_container, tmp_path: Path) -> None:
    """Attempt the real PostgreSQL bootstrap only when explicitly enabled.

    The current repository SQL conversion is intentionally a follow-up boundary;
    this test is the manual integration hook that exposes any remaining dialect
    incompatibility during a controlled migration run.
    """
    settings = SystemSettings(
        _env_file=None,
        db_driver="postgres",
        db_dsn=postgres_container.get_connection_url(),
        db_path=str(tmp_path / "unused.sqlite"),
    )
    from multiscribe_agent.bootstrap import ServiceContext

    context = ServiceContext(settings)
    await context.init()
    await context.close()
