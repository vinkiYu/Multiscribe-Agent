"""P41 approve/reject endpoint behavior without external publisher calls."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from multiscribe_agent.api.routes.digest import approve_digest, reject_digest
from multiscribe_agent.config import SystemSettings
from multiscribe_agent.core.daily_digest_archive import DailyDigestArchive
from multiscribe_agent.infra.db import Database, init_db
from multiscribe_agent.renderers.feishu_card import DigestItem
from multiscribe_agent.renderers.models import CuratedDigest


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


def _context(db: Database, publishing: FakePublishing, entities: FakeEntities) -> SimpleNamespace:
    """Build the minimal ServiceContext-shaped object consumed by the routes."""
    return SimpleNamespace(
        db=db,
        publishing=publishing,
        entities=entities,
        pushed_content=FakePushedContent(),
        settings=SystemSettings(_env_file=None),
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
        )

        result = await approve_digest("2026-07-29", context)  # type: ignore[arg-type]

        assert result["status"] == "approved"
        assert publishing.calls == [["wecom_bot"]]
        assert await archive.get_approval_status(db, "2026-07-29") == "approved"
        assert len(context.pushed_content.records) == 1
    finally:
        await db.close()


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
