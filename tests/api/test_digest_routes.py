"""P41 approve/reject endpoint behavior without external publisher calls."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import multiscribe_agent.bootstrap as bootstrap_module
from multiscribe_agent.agents.pipelines.daily_digest import digest_content_hash
from multiscribe_agent.api.routes.digest import approve_digest, reject_digest, run_digest
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings
from multiscribe_agent.core.daily_digest_archive import DailyDigestArchive
from multiscribe_agent.core.publish_history import PublishHistory
from multiscribe_agent.domain.models import AgentDefinition, ScheduleTask
from multiscribe_agent.infra.db import Database, init_db
from multiscribe_agent.renderers.feishu_card import DigestItem
from multiscribe_agent.renderers.models import CuratedDigest
from multiscribe_agent.services.scheduler_lock import AcquireResult


class FakePublishing:
    """Record approval fan-out targets and report successful deliveries."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def fanout(
        self, digest: CuratedDigest, targets: list[str]
    ) -> dict[str, dict[str, object]]:
        """Return one successful outcome per requested target."""
        del digest
        self.calls.append(targets)
        return {target: {"status": "success"} for target in targets}


class FakeEntities:
    """Expose the persisted daily schedule used for target resolution."""

    def __init__(self, config: dict[str, object]) -> None:
        self._config = config

    async def list_all(self, table: str) -> list[dict[str, object]]:
        """Return one schedule document."""
        assert table == "schedules"
        return [{"task_type": "daily_digest", "config": self._config}]


class FakePushedContent:
    """Record content identities written after final approval."""

    def __init__(self) -> None:
        self.records: list[tuple[str, str, str]] = []

    async def add(
        self,
        db: Database,
        *,
        content_hash: str,
        url: str,
        digest_date: str,
        title: str,
    ) -> None:
        """Store the approval identity while ignoring the database handle."""
        del db
        self.records.append((content_hash, url, digest_date + ":" + title))


class FakeApprovalLock:
    """Return a configured approval-lock result and record lease operations."""

    def __init__(self, result: AcquireResult) -> None:
        self.result = result
        self.acquire_calls: list[tuple[str, int]] = []
        self.release_calls: list[tuple[str, str]] = []

    async def acquire(self, key: str, ttl_seconds: int) -> AcquireResult:
        """Record the requested date-scoped key and return the fake result."""
        self.acquire_calls.append((key, ttl_seconds))
        return self.result

    async def release(self, key: str, token: str) -> None:
        """Record owner-token release after the approval operation."""
        self.release_calls.append((key, token))


class FakeDigestScheduler:
    """Capture manual digest execution and return a configured scheduler result."""

    def __init__(self, result: dict[str, object] | None) -> None:
        self.result = result
        self.calls: list[tuple[ScheduleTask, object]] = []

    async def execute_task(self, task: ScheduleTask, callback: object) -> dict[str, object] | None:
        """Record the callback boundary used by the route."""
        self.calls.append((task, callback))
        return self.result


def _context(
    db: Database,
    publishing: FakePublishing,
    entities: FakeEntities,
    scheduler_lock: FakeApprovalLock | None = None,
    publish_history: PublishHistory | None = None,
) -> SimpleNamespace:
    """Build the minimal ServiceContext-shaped object consumed by the routes."""
    return SimpleNamespace(
        db=db,
        publishing=publishing,
        entities=entities,
        pushed_content=FakePushedContent(),
        settings=SystemSettings(_env_file=None),
        scheduler_lock=scheduler_lock,
        publish_history=publish_history,
    )


def _digest() -> CuratedDigest:
    """Build one archived digest snapshot."""
    return CuratedDigest(
        date="2026-07-29",
        title="Daily AI",
        summary="Overview",
        total_scanned=1,
        items=[
            DigestItem(
                title="Agent article",
                summary="A useful summary.",
                url="https://example.test/article",
                source="RSS",
                score=9.0,
            )
        ],
    )


@pytest.mark.asyncio
async def test_approve_rebuilds_digest_excludes_preview_and_records_pushed_content() -> None:
    """Approval sends only final targets, marks approved, and writes P35 identities."""
    db = await init_db(":memory:")
    try:
        archive = DailyDigestArchive()
        await archive.upsert(db, _digest(), approval_status="pending")
        publishing = FakePublishing()
        context = _context(
            db,
            publishing,
            FakeEntities(
                {"targets": ["feishu_bot", "wecom_bot"], "preview_targets": ["feishu_bot"]}
            ),
            publish_history=PublishHistory(),
        )

        result = await approve_digest("2026-07-29", context)  # type: ignore[arg-type]

        assert result["status"] == "approved"
        assert publishing.calls == [["wecom_bot"]]
        assert await archive.get_approval_status(db, "2026-07-29") == "approved"
        assert len(context.pushed_content.records) == 1
        assert context.pushed_content.records[0][0] == digest_content_hash(
            "Agent article", "A useful summary."
        )
        records = await context.publish_history.query(db, digest_date="2026-07-29")
        assert len(records) == 1
        assert records[0].content_hash == context.pushed_content.records[0][0]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_manual_digest_route_uses_scheduler_and_returns_callback_result() -> None:
    """Manual runs share the scheduler lock boundary instead of calling the pipeline directly."""
    scheduler = FakeDigestScheduler({"result_count": 1})

    async def callback(task: ScheduleTask, *, run_id: str) -> dict[str, object]:
        del task, run_id
        return {"result_count": 1}

    context = SimpleNamespace(scheduler=scheduler, run_daily_digest_task=callback, entities=None)

    result = await run_digest({"targets": []}, context)  # type: ignore[arg-type]

    assert result == {"result_count": 1}
    assert len(scheduler.calls) == 1
    assert scheduler.calls[0][0].id == "manual-daily-digest"
    assert scheduler.calls[0][0].task_type == "daily_digest"


@pytest.mark.asyncio
async def test_manual_digest_route_maps_scheduler_skip_to_conflict() -> None:
    """A held daily-digest lease is exposed as an explicit HTTP conflict."""
    context = SimpleNamespace(
        scheduler=FakeDigestScheduler(None),
        run_daily_digest_task=lambda task, *, run_id: None,
        entities=None,
    )

    with pytest.raises(HTTPException) as error:
        await run_digest({}, context)  # type: ignore[arg-type]

    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_direct_daily_digest_task_uses_valid_payload_date_for_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Direct callers can provide a real date while scheduler run IDs remain authoritative."""
    captured: dict[str, object] = {}

    class Entities:
        async def get(self, table: str, entity_id: str) -> dict[str, object] | None:
            assert table == "agents"
            assert entity_id == "curator"
            return AgentDefinition(
                id="curator",
                name="Curator",
                description="test",
                system_prompt="test",
                provider_id="provider",
                model="model",
            ).model_dump(mode="json")

    class Pipeline:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def run(
            self, *, run_date: str | None, workflow_run_id: str | None
        ) -> dict[str, object]:
            captured["run_date"] = run_date
            captured["workflow_run_id"] = workflow_run_id
            return {"result_count": 0}

    monkeypatch.setattr(bootstrap_module, "DailyDigestPipeline", Pipeline)
    context = ServiceContext(SystemSettings(_env_file=None))
    context._initialized = True
    context.entities = Entities()  # type: ignore[assignment]
    context._provider_for_agent = lambda definition: object()  # type: ignore[method-assign]

    result = await context.run_daily_digest_task(
        ScheduleTask(
            id="manual",
            name="Manual",
            task_type="daily_digest",
            cron="0 0 * * *",
            config={"curate_agent_id": "curator", "date": "2026-01-02"},
        )
    )

    assert result == {"result_count": 0}
    assert captured == {"run_date": "2026-01-02", "workflow_run_id": "manual:2026-01-02"}

    with pytest.raises(ValueError, match="valid calendar date"):
        await context.run_daily_digest_task(
            ScheduleTask(
                id="manual",
                name="Manual",
                task_type="daily_digest",
                cron="0 0 * * *",
                config={"curate_agent_id": "curator", "date": "2026-02-30"},
            )
        )


@pytest.mark.asyncio
async def test_reject_marks_pending_digest_without_fanout() -> None:
    """Reject is a terminal state and never calls the publisher service."""
    db = await init_db(":memory:")
    try:
        archive = DailyDigestArchive()
        await archive.upsert(db, _digest(), approval_status="pending")
        publishing = FakePublishing()
        context = _context(db, publishing, FakeEntities({"targets": ["wecom_bot"]}))

        result = await reject_digest("2026-07-29", context)  # type: ignore[arg-type]

        assert result == {"status": "rejected", "date": "2026-07-29"}
        assert publishing.calls == []
        assert await archive.get_approval_status(db, "2026-07-29") == "rejected"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_approve_missing_or_non_pending_digest_returns_http_error() -> None:
    """Approval rejects missing dates and already terminal states explicitly."""
    db = await init_db(":memory:")
    try:
        publishing = FakePublishing()
        context = _context(db, publishing, FakeEntities({"targets": ["wecom_bot"]}))
        with pytest.raises(HTTPException) as missing:
            await approve_digest("2026-07-28", context)  # type: ignore[arg-type]
        assert missing.value.status_code == 404

        archive = DailyDigestArchive()
        await archive.upsert(db, _digest(), approval_status="published")
        with pytest.raises(HTTPException) as published:
            await approve_digest("2026-07-29", context)  # type: ignore[arg-type]
        assert published.value.status_code == 409
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_approve_uses_date_scoped_lock_and_releases_owner_token() -> None:
    """Approval holds a five-minute lease for the digest date and releases it."""
    db = await init_db(":memory:")
    try:
        archive = DailyDigestArchive()
        await archive.upsert(db, _digest(), approval_status="pending")
        lock = FakeApprovalLock(AcquireResult(acquired=True, token="owner-token"))
        context = _context(db, FakePublishing(), FakeEntities({"targets": ["wecom_bot"]}), lock)

        await approve_digest("2026-07-29", context)  # type: ignore[arg-type]

        assert lock.acquire_calls == [("multiscribe:digest:approve:2026-07-29", 300)]
        assert lock.release_calls == [("multiscribe:digest:approve:2026-07-29", "owner-token")]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_approve_rejects_when_lock_is_held_or_unavailable_in_strict_mode() -> None:
    """A held or unavailable strict lock prevents fan-out before archive inspection."""
    db = await init_db(":memory:")
    try:
        archive = DailyDigestArchive()
        await archive.upsert(db, _digest(), approval_status="pending")
        for lock_result in (
            AcquireResult(acquired=False, reason="already_locked"),
            AcquireResult(acquired=False, reason="redis_unreachable", unavailable=True),
        ):
            publishing = FakePublishing()
            context = _context(
                db,
                publishing,
                FakeEntities({"targets": ["wecom_bot"]}),
                FakeApprovalLock(lock_result),
            )
            with pytest.raises(HTTPException) as error:
                await approve_digest("2026-07-29", context)  # type: ignore[arg-type]
            assert error.value.status_code == 409
            assert publishing.calls == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_approve_allows_lock_unavailable_when_configured_for_relaxed_mode() -> None:
    """A relaxed lock result preserves the configured availability degradation."""
    db = await init_db(":memory:")
    try:
        archive = DailyDigestArchive()
        await archive.upsert(db, _digest(), approval_status="pending")
        lock = FakeApprovalLock(
            AcquireResult(
                acquired=False,
                reason="redis_unreachable",
                unavailable=True,
                allow_without_lock=True,
            )
        )
        context = _context(db, FakePublishing(), FakeEntities({"targets": ["wecom_bot"]}), lock)

        result = await approve_digest("2026-07-29", context)  # type: ignore[arg-type]

        assert result["status"] == "approved"
        assert lock.release_calls == []
    finally:
        await db.close()
