"""Manual daily-digest pipeline trigger."""
# ruff: noqa: B008

from __future__ import annotations

import json
from collections.abc import Mapping

from fastapi import APIRouter, Depends, HTTPException

from multiscribe_agent.agents.pipelines.daily_digest import digest_content_hash
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
    """Execute P11 immediately through the scheduler's shared idempotency boundary."""
    if context.scheduler is None:
        raise HTTPException(status_code=503, detail="scheduler is unavailable")
    curator_id = payload.get("curate_agent_id")
    entities = getattr(context, "entities", None)
    if (
        isinstance(curator_id, str)
        and entities is not None
        and await entities.get("agents", curator_id) is None
    ):
        raise HTTPException(status_code=400, detail=f"agent not found: {curator_id}")
    task = ScheduleTask(
        id="manual-daily-digest",
        name="Manual daily digest",
        task_type="daily_digest",
        cron="0 0 * * *",
        config=payload,
    )
    try:
        result = await context.scheduler.execute_task(task, context.run_daily_digest_task)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=409,
            detail="digest already running today (lock held) or scheduler lock unavailable",
        )
    return result


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
    if context.db is None or not any(
        result.get("status") == "success" for result in results.values()
    ):
        return
    hashes = [digest_content_hash(item.title, item.summary) for item in archived.items]
    unique_hashes = list(dict.fromkeys(hashes))
    serialized_hashes = (
        unique_hashes[0]
        if len(unique_hashes) == 1
        else json.dumps(unique_hashes, separators=(",", ":"))
    )
    if context.pushed_content is not None:
        for item, content_hash in zip(archived.items, hashes, strict=True):
            await context.pushed_content.add(
                context.db,
                content_hash=content_hash,
                url=item.url,
                digest_date=archived.date,
                title=item.title,
            )
    publish_history = getattr(context, "publish_history", None)
    if publish_history is None:
        return
    for publisher_id, result in results.items():
        if result.get("status") != "success":
            continue
        await publish_history.add(
            context.db,
            publisher_id=publisher_id,
            status="success",
            title=archived.title,
            content=archived.summary,
            result_data=result,
            digest_date=archived.date,
            content_hash=serialized_hashes,
        )
