"""Tests for SQL write auditing and suspicious-pattern detection."""

from __future__ import annotations

import pytest

from multiscribe_agent.infra.db import init_db
from multiscribe_agent.observability.sql_audit import SqlAuditLogger


@pytest.mark.asyncio
async def test_write_operations_are_recorded_without_audit_recursion() -> None:
    """INSERT/UPDATE/DELETE writes produce audit rows while the audit INSERT is skipped."""
    db = await init_db(":memory:")
    try:
        audit = SqlAuditLogger(db)
        db.set_audit_logger(audit)
        await db.execute("INSERT INTO kv(key, value) VALUES (?, ?)", ("a", "1"))
        await db.execute("UPDATE kv SET value = ? WHERE key = ?", ("2", "a"))
        await db.execute("DELETE FROM kv WHERE key = ?", ("a",))

        rows = await db.fetchall("SELECT operation FROM sql_audit_log ORDER BY id")
        assert [str(row["operation"]) for row in rows] == ["INSERT", "UPDATE", "DELETE"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_suspicious_sql_is_flagged_and_warned(monkeypatch) -> None:
    """DROP/UNION/comment patterns are reported without executing dynamic SQL."""
    db = await init_db(":memory:")
    try:
        audit = SqlAuditLogger(db)
        warnings: list[dict[str, object]] = []
        monkeypatch.setattr(
            "multiscribe_agent.observability.sql_audit.log.warning",
            lambda event, **kwargs: warnings.append({"event": event, **kwargs}),
        )
        entry = await audit.record("DROP TABLE users --", ())
        assert entry.suspicious is True
        assert "DROP" in entry.suspicious_patterns
        assert warnings[0]["event"] == "suspicious_sql_detected"
    finally:
        await db.close()
