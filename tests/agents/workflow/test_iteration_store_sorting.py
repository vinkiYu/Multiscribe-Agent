"""Regression coverage for durable Loop checkpoint ordering."""

from __future__ import annotations

import pytest

from multiscribe_agent.agents.workflow.iteration_store import IterationRecord, IterationStore
from multiscribe_agent.infra.db import init_db


@pytest.mark.asyncio
async def test_list_recent_orders_by_epoch_timestamp_newest_first() -> None:
    """Equal-width epoch strings retain numeric newest-first ordering in SQLite."""
    db = await init_db(":memory:")
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
            # Legacy rows may carry epoch text; current INTEGER affinity stores the
            # same values numerically while preserving the ordering contract.
            await db.execute(
                "UPDATE workflow_iterations SET recorded_at = ? WHERE workflow_run_id = ?",
                (timestamp, f"run-{index}"),
            )

        recent = await store.list_recent(limit=3)
        assert [record.workflow_run_id for record in recent] == ["run-2", "run-1", "run-0"]
    finally:
        await db.close()
