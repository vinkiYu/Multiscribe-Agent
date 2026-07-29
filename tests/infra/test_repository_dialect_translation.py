"""Static guardrails ensuring repository SQL goes through dialect helpers."""

from __future__ import annotations

from pathlib import Path

ROOT = Path("src/multiscribe_agent")
TARGETS = (
    "infra/repositories/api_key.py",
    "infra/repositories/curation_evaluations.py",
    "infra/repositories/daily_usage.py",
    "infra/repositories/entity_json.py",
    "infra/repositories/kv.py",
    "infra/repositories/source_data.py",
    "infra/repositories/task_log.py",
    "core/adapter_health.py",
    "core/click_events.py",
    "core/daily_digest_archive.py",
    "core/publish_history.py",
    "core/pushed_content.py",
    "memory/repositories/memory_categories.py",
    "memory/repositories/memory_entries.py",
    "knowledge/kb_service.py",
    "knowledge/retriever.py",
    "knowledge/vector_store.py",
)


def test_repository_calls_do_not_bypass_dialect_helpers() -> None:
    """No whitelisted business module may call the database object directly."""
    for relative_path in TARGETS:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "DialectMixin" in source or "DialectRepositoryMixin" in source
        for method in ("execute", "executemany", "fetchone", "fetchall"):
            assert f"self._db.{method}(" not in source, relative_path
            assert f"db.{method}(" not in source, relative_path


def test_explicit_db_services_use_explicit_helper_calls() -> None:
    """Legacy services receiving db per method still route through the mixin."""
    for relative_path in (
        "core/adapter_health.py",
        "core/click_events.py",
        "core/daily_digest_archive.py",
        "core/publish_history.py",
        "core/pushed_content.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "ExplicitDatabaseDialectMixin" in source
        assert "self._execute(" in source or "self._fetchall(" in source
