"""PostgreSQL SQL translation for IterationStore without a live server."""

from __future__ import annotations

import pytest

from multiscribe_agent.agents.workflow.iteration_store import IterationRecord, IterationStore
from multiscribe_agent.infra.db_protocol import PlaceholderStyle


class _PostgresCapture:
    """Capture translated SQL without requiring a live PostgreSQL server."""

    placeholder_style = PlaceholderStyle.DOLLAR

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, statement: str, parameters: tuple[object, ...] = ()) -> int:
        """Record one translated statement."""
        self.executed.append((statement, parameters))
        return 1

    async def fetchall(
        self, statement: str, parameters: tuple[object, ...] = ()
    ) -> list[dict[str, object]]:
        """Return no rows after recording the translated query."""
        self.executed.append((statement, parameters))
        return []

    async def fetchone(
        self, statement: str, parameters: tuple[object, ...] = ()
    ) -> dict[str, object] | None:
        """Return no row after recording a translated single-row query."""
        self.executed.append((statement, parameters))
        return None


def _record(round_number: int = 1) -> IterationRecord:
    """Build one iteration record for SQL capture tests."""
    return IterationRecord(
        workflow_run_id="run-1",
        step_id="curate",
        round=round_number,
        output="curated output",
        score=8.5,
        feedback="good",
        converged=False,
        reason="continue",
    )


@pytest.mark.asyncio
async def test_append_translates_to_postgres_upsert_with_triple_conflict_target() -> None:
    """The composite run/step/round conflict target survives translation."""
    database = _PostgresCapture()
    store = IterationStore(database)  # type: ignore[arg-type]

    await store.append(_record())

    upsert_sql = database.executed[0][0]
    assert "ON CONFLICT (workflow_run_id, step_id, round) DO UPDATE" in upsert_sql
    assert all(f"${index}" in upsert_sql for index in range(1, 9))
    assert "output = excluded.output" in upsert_sql
    assert "reason = excluded.reason" in upsert_sql


@pytest.mark.asyncio
async def test_list_for_step_translates_to_postgres_parameterized_query() -> None:
    """list_for_step uses numbered placeholders and ASC round ordering."""
    database = _PostgresCapture()
    store = IterationStore(database)  # type: ignore[arg-type]

    await store.list_for_step("run-1", "curate")

    query_sql = database.executed[0][0]
    assert "workflow_run_id = $1 AND step_id = $2" in query_sql
    assert "ORDER BY round ASC" in query_sql


@pytest.mark.asyncio
async def test_resume_loop_translates_to_postgres_latest_checkpoint_query() -> None:
    """resume_loop without a step ID queries the newest checkpoint across steps."""
    database = _PostgresCapture()
    store = IterationStore(database)  # type: ignore[arg-type]

    await store.resume_loop("run-1")

    query_sql = database.executed[0][0]
    assert "workflow_run_id = $1" in query_sql
    assert "ORDER BY recorded_at DESC, round DESC" in query_sql
    assert "LIMIT 1" in query_sql
