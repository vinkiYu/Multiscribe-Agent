"""Authenticated REST endpoints for user preferences and durable memories."""

from __future__ import annotations

from time import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.domain.models import MemoryEntry
from multiscribe_agent.memory.memory_service import MemoryService
from multiscribe_agent.memory.preference_store import UserPreferences

router = APIRouter(prefix="/api/memory", tags=["memory"], dependencies=[Depends(get_current_user)])


@router.get("/preferences")
async def get_preferences(
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Return persisted recommendation and delivery preferences."""
    return _preferences_response(await _service(context).get_preferences())


@router.put("/preferences")
async def save_preferences(
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Replace the complete preference object after input validation."""
    try:
        preferences = UserPreferences(
            _string_list(payload, "preferred_tags"),
            _string_list(payload, "block_sources"),
            _text(payload, "push_time"),
            _integer(payload, "importance_threshold"),
            blocked_topics=_string_list(payload, "blocked_topics"),
        )
        await _service(context).save_preferences(preferences)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _preferences_response(preferences)


@router.get("/entries/search")
async def search_entries(
    q: str,
    limit: int = Query(default=20, ge=1, le=50),
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> list[dict[str, object]]:
    """Search durable memory content through FTS5."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="q must not be empty")
    return [_entry_response(entry) for entry in await _service(context).search_entries(q, limit)]


@router.get("/entries")
async def list_entries(
    category: str | None = None,
    tag: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> list[dict[str, object]]:
    """List durable memory entries with optional filters."""
    entries = await _service(context).list_entries(category, tag, limit)
    return [_entry_response(entry) for entry in entries]


@router.post("/entries")
async def create_entry(
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Create a memory entry and return the canonical id after deduplication."""
    try:
        entry = MemoryEntry(
            id=str(uuid4()),
            content=_text(payload, "content"),
            importance=_integer(payload, "importance", default=5),
            tags=_string_list(payload, "tags"),
            created_at=int(time()),
            agent_id=payload.get("agent_id") if isinstance(payload.get("agent_id"), str) else None,
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    entry_id = await _service(context).add_entry(entry)
    return {"id": entry_id}


@router.delete("/entries/{entry_id}")
async def delete_entry(
    entry_id: str,
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, str]:
    """Delete one memory entry."""
    if not await _service(context).delete_entry(entry_id):
        raise HTTPException(status_code=404, detail="memory entry not found")
    return {"status": "deleted"}


@router.post("/extract")
async def extract_from_history(
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Extract recent publish-history preferences and merge unique entries."""
    days = _integer(payload, "days", default=30)
    return {"extracted": await _service(context).extract_and_merge(days)}


def _service(context: ServiceContext) -> MemoryService:
    if context.memory_service is None:
        raise HTTPException(status_code=503, detail="memory service unavailable")
    return context.memory_service


def _preferences_response(preferences: UserPreferences) -> dict[str, object]:
    return {
        "preferred_tags": preferences.preferred_tags,
        "block_sources": preferences.block_sources,
        "blocked_topics": preferences.blocked_topics,
        "push_time": preferences.push_time,
        "importance_threshold": preferences.importance_threshold,
    }


def _entry_response(entry: MemoryEntry) -> dict[str, object]:
    return entry.model_dump(mode="json")


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _integer(payload: dict[str, object], key: str, default: int | None = None) -> int:
    value = payload.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _string_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a string list")
    return list(value)
