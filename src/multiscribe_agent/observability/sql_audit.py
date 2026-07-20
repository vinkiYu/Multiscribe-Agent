"""Append-only SQL audit log with suspicious-pattern detection."""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from dataclasses import dataclass

import structlog

from multiscribe_agent.infra.db import Database

log = structlog.get_logger(__name__)

SUSPICIOUS_PATTERNS = (
    ("DROP", re.compile(r"\bDROP\b", re.IGNORECASE)),
    ("UNION SELECT", re.compile(r"\bUNION\b\s+SELECT", re.IGNORECASE)),
    ("--", re.compile(r"--", re.IGNORECASE)),
    ("TRUNCATE", re.compile(r"\bTRUNCATE\b", re.IGNORECASE)),
)


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One bounded SQL audit record."""

    statement: str
    operation: str
    param_count: int
    suspicious: bool
    suspicious_patterns: list[str]
    recorded_at: int


class SqlAuditLogger:
    """Persist write-operation audit entries and flag suspicious SQL patterns."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def record(self, statement: str, parameters: Sequence[object] = ()) -> AuditEntry:
        """Record a write statement and emit a warning when patterns look suspicious."""
        operation = self._classify(statement)
        patterns = [label for label, pattern in SUSPICIOUS_PATTERNS if pattern.search(statement)]
        entry = AuditEntry(
            statement=statement[:500],
            operation=operation,
            param_count=len(parameters),
            suspicious=bool(patterns),
            suspicious_patterns=patterns,
            recorded_at=int(time.time()),
        )
        if operation in {"INSERT", "UPDATE", "DELETE"}:
            await self._db.execute(
                """
                INSERT INTO sql_audit_log
                    (
                        statement,
                        operation,
                        param_count,
                        suspicious,
                        suspicious_patterns,
                        recorded_at
                    )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.statement,
                    entry.operation,
                    entry.param_count,
                    int(entry.suspicious),
                    ",".join(entry.suspicious_patterns),
                    entry.recorded_at,
                ),
            )
        if entry.suspicious:
            log.warning(
                "suspicious_sql_detected",
                statement=entry.statement,
                operation=entry.operation,
                patterns=entry.suspicious_patterns,
            )
        return entry

    @staticmethod
    def _classify(statement: str) -> str:
        """Classify the leading SQL operation without executing the statement."""
        stripped = statement.lstrip().upper()
        for operation in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"):
            if stripped.startswith(operation):
                return operation
        return "OTHER"
