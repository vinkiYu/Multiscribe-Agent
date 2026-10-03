"""Regression coverage for durable Loop checkpoint ordering."""

from __future__ import annotations

import pytest

from multiscribe_agent.agents.workflow.iteration_store import IterationRecord, IterationStore
from tests.db import init_test_database


@pytest.mark.asyncio
async def test_list_recent_orders_by_epoch_timestamp_newest_first() -> None:
    """Equal-width epoch values retain numeric newest-first ordering."""
    db = await init_test_database()
    try:
        store = IterationStore(db)
        for index, timestamp in enumerate(("1722681600", "1722681601", "1722681602")):
            await store.append(
                IterationRecord(
                    workflow_run_id=f"run-{index}",
                    step_id="curate",
                    round=1,
                    output=f"output-{index}",
                    score=None,
                    feedback=None,
                    converged=False,
                    reason="max_rounds",
                )
            )
            # Legacy rows may carry epoch text; PostgreSQL stores timestamps as
            # BIGINT, so the numeric value preserves the ordering contract.
            await db.execute(
                "UPDATE workflow_iterations SET recorded_at = $1 WHERE workflow_run_id = $2",
                (int(timestamp), f"run-{index}"),
            )

        recent = await store.list_recent(limit=3)
        assert [record.workflow_run_id for record in recent] == ["run-2", "run-1", "run-0"]
    finally:
        await db.close()
