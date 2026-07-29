"""Manual daily-digest pipeline trigger."""
# ruff: noqa: B008

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from fastapi import APIRouter, Depends, HTTPException

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.core.daily_digest_archive import ArchivedDigest, get_daily_digest_archive
from multiscribe_agent.domain.models import ScheduleTask
from multiscribe_agent.renderers.feishu_card import DigestItem
from multiscribe_agent.renderers.models import CuratedDigest
from multiscribe_agent.services.scheduler_lock import AcquireResult

router = APIRouter(prefix="/api/digest", tags=["digest"], dependencies=[Depends(get_current_user)])


@router.post("/run")
async def run_digest(
    payload: dict[str, object], context: ServiceContext = Depends(get_context)
) -> dict[str, object]:
    """Execute P11 immediately using an API-provided daily-digest configuration."""
    task = ScheduleTask(
        id="manual-daily-digest",
        name="Manual daily digest",
        task_type="daily_digest",
        cron="0 0 * * *",
        config=payload,
    )
    try:
        return await context.run_daily_digest_task(task)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{date}/approve")
async def approve_digest(
    date: str,
    context: ServiceContext = Depends(get_context),
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    """Approve a pending preview and publish it to the remaining targets."""
    lock = getattr(context, "scheduler_lock", None)
    lock_result: AcquireResult | None = None
    if lock is not None:
        lock_result = await lock.acquire(f"multiscribe:digest:approve:{date}", ttl_seconds=300)
        if not lock_result.acquired and not lock_result.allow_without_lock:
            detail = (
                "digest is already being approved"
                if lock_result.reason == "already_locked"
                else "digest approval lock is unavailable"
            )
            raise HTTPException(status_code=409, detail=detail)
    try:
        archived = await _pending_archive(context, date)
        targets = await _resolve_broadcast_targets(context, payload)
        db = context.db
        if context.publishing is None or db is None:
            raise HTTPException(status_code=503, detail="digest services are unavailable")
        digest = _rebuild_curated_digest(archived)
        results = await context.publishing.fanout(digest, targets)
        await get_daily_digest_archive().set_approval_status(db, date, "approved")
        await _record_approved_content(context, archived, results)
        return {"status": "approved", "targets": results}
    finally:
        if (
            lock is not None
            and lock_result is not None
            and lock_result.acquired
            and lock_result.token is not None
        ):
            await lock.release(f"multiscribe:digest:approve:{date}", lock_result.token)


@router.post("/{date}/reject")
async def reject_digest(
    date: str,
    context: ServiceContext = Depends(get_context),
) -> dict[str, object]:
    """Reject a pending preview without sending it to any additional target."""
    await _pending_archive(context, date)
    if context.db is None:
        raise HTTPException(status_code=503, detail="database is unavailable")
    await get_daily_digest_archive().set_approval_status(context.db, date, "rejected")
    return {"status": "rejected", "date": date}


async def _pending_archive(context: ServiceContext, digest_date: str) -> ArchivedDigest:
    """Load one archive and enforce the pending-only approval transition."""
    if context.db is None:
        raise HTTPException(status_code=503, detail="database is unavailable")
    try:
        archived = await get_daily_digest_archive().get(context.db, digest_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if archived is None:
        raise HTTPException(status_code=404, detail="no digest found for this date")
    if archived.approval_status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"digest is not pending approval (status={archived.approval_status})",
        )
    return archived


async def _resolve_broadcast_targets(
    context: ServiceContext, payload: Mapping[str, object] | None
) -> list[str]:
    """Resolve configured targets and remove preview destinations before approval fan-out."""
    explicit_targets = _optional_string_list(payload, "targets")
    explicit_preview = _optional_string_list(payload, "preview_targets")
    configured_targets: list[str] | None = explicit_targets
    configured_preview: list[str] | None = explicit_preview
    if context.entities is not None and (configured_targets is None or configured_preview is None):
        schedules = await context.entities.list_all("schedules")
        for schedule in schedules:
            if schedule.get("task_type") != "daily_digest":
                continue
            raw_config = schedule.get("config")
            if not isinstance(raw_config, Mapping):
                continue
            if configured_targets is None:
                configured_targets = _optional_string_list(raw_config, "targets")
            if configured_preview is None:
                configured_preview = _optional_string_list(raw_config, "preview_targets")
            if configured_targets is not None or configured_preview is not None:
                break
    if configured_targets is None:
        configured_targets = [
            publisher.id for publisher in context.settings.publishers if publisher.enabled
        ]
    if configured_preview is None:
        configured_preview = []
    return list(
        dict.fromkeys(target for target in configured_targets if target not in configured_preview)
    )


def _optional_string_list(payload: Mapping[str, object] | None, key: str) -> list[str] | None:
    """Read an optional non-empty string list from an API or schedule payload."""
    if payload is None or key not in payload:
        return None
    raw_value = payload[key]
    if not isinstance(raw_value, list) or not all(
        isinstance(value, str) and value.strip() for value in raw_value
    ):
        raise HTTPException(status_code=400, detail=f"{key} must be a list of non-empty strings")
    return list(dict.fromkeys(raw_value))


def _rebuild_curated_digest(archived: ArchivedDigest) -> CuratedDigest:
    """Rebuild a publishable digest from the immutable preview archive snapshot."""
    return CuratedDigest(
        date=archived.date,
        title=archived.title,
        summary=archived.summary,
        total_scanned=archived.total_scanned,
        items=[
            DigestItem(
                title=item.title,
                summary=item.summary,
                url=item.url,
                source=item.source,
                score=item.score,
                image_url=item.image_url,
                video_url=item.video_url,
                published_at=item.published_at,
                section=item.section,
                tags=item.tags,
            )
            for item in archived.items
        ],
    )


async def _record_approved_content(
    context: ServiceContext,
    archived: ArchivedDigest,
    results: Mapping[str, Mapping[str, object]],
) -> None:
    """Record approved items only after at least one final target accepted the digest."""
    if (
        context.db is None
        or context.pushed_content is None
        or not any(result.get("status") == "success" for result in results.values())
    ):
        return
    for item in archived.items:
        content_hash = hashlib.sha256(f"{item.title}\n{item.summary}".encode()).hexdigest()
        await context.pushed_content.add(
            context.db,
            content_hash=content_hash,
            url=item.url,
            digest_date=archived.date,
            title=item.title,
        )
