"""Persist Loop node iterations for crash recovery and workflow auditing."""

from __future__ import annotations

from dataclasses import dataclass

from multiscribe_agent.infra.db import Database


@dataclass(frozen=True, slots=True)
class IterationRecord:
    """Durable result of one Loop node round."""

    workflow_run_id: str
    step_id: str
    round: int
    output: str
    score: float | None
    feedback: str | None
    converged: bool
    reason: str


class IterationStore:
    """CRUD wrapper for the ``workflow_iterations`` table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def append(self, record: IterationRecord) -> None:
        """Insert one iteration row, replacing an interrupted duplicate round."""
        await self._db.execute(
            """
            INSERT INTO workflow_iterations
                (workflow_run_id, step_id, round, output, score, feedback, converged, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_run_id, step_id, round) DO UPDATE SET
                output = excluded.output,
                score = excluded.score,
                feedback = excluded.feedback,
                converged = excluded.converged,
                reason = excluded.reason
            """,
            (
                record.workflow_run_id,
                record.step_id,
                record.round,
                record.output[:8000],
                record.score,
                record.feedback,
                int(record.converged),
                record.reason,
            ),
        )

    async def list_for_step(self, workflow_run_id: str, step_id: str) -> list[IterationRecord]:
        """Return all iterations for one step, ordered by round."""
        rows = await self._db.fetchall(
            """
            SELECT workflow_run_id, step_id, round, output, score, feedback, converged, reason
            FROM workflow_iterations
            WHERE workflow_run_id = ? AND step_id = ?
            ORDER BY round ASC
            """,
            (workflow_run_id, step_id),
        )
        return [self._from_row(row) for row in rows]

    async def latest_for_step(self, workflow_run_id: str, step_id: str) -> IterationRecord | None:
        """Return the latest durable iteration for a step, if one exists."""
        rows = await self._db.fetchall(
            """
            SELECT workflow_run_id, step_id, round, output, score, feedback, converged, reason
            FROM workflow_iterations
            WHERE workflow_run_id = ? AND step_id = ?
            ORDER BY round DESC
            LIMIT 1
            """,
            (workflow_run_id, step_id),
        )
        return self._from_row(rows[0]) if rows else None

    async def resume_loop(
        self, workflow_run_id: str, step_id: str | None = None
    ) -> IterationRecord | None:
        """Return the latest checkpoint used to resume a workflow run.

        When ``step_id`` is omitted, the latest checkpoint across all Loop steps is
        returned. Callers that resume a specific step should pass its ID.
        """
        if step_id is not None:
            return await self.latest_for_step(workflow_run_id, step_id)
        rows = await self._db.fetchall(
            """
            SELECT workflow_run_id, step_id, round, output, score, feedback, converged, reason
            FROM workflow_iterations
            WHERE workflow_run_id = ?
            ORDER BY recorded_at DESC, round DESC
            LIMIT 1
            """,
            (workflow_run_id,),
        )
        return self._from_row(rows[0]) if rows else None

    @staticmethod
    def _from_row(row: object) -> IterationRecord:
        """Convert an aiosqlite row into the domain record."""
        return IterationRecord(
            workflow_run_id=str(row["workflow_run_id"]),  # type: ignore[index]
            step_id=str(row["step_id"]),  # type: ignore[index]
            round=int(row["round"]),  # type: ignore[index]
            output=str(row["output"]),  # type: ignore[index]
            score=float(row["score"]) if row["score"] is not None else None,  # type: ignore[index]
            feedback=str(row["feedback"]) if row["feedback"] is not None else None,  # type: ignore[index]
            converged=bool(row["converged"]),  # type: ignore[index]
            reason=str(row["reason"]),  # type: ignore[index]
        )
