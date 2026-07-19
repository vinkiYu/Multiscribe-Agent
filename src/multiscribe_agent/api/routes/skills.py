"""Authenticated REST endpoints for builtin and custom Skill documents."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.domain.models import SkillEntry
from multiscribe_agent.skills.service import SkillService

router = APIRouter(prefix="/api/skills", tags=["skills"], dependencies=[Depends(get_current_user)])


@router.get("")
async def list_skills(
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> list[dict[str, object]]:
    """List all currently loaded builtin and custom skills."""
    return [_response(entry) for entry in _service(context).list()]


@router.post("/reload")
async def reload_skills(
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, int]:
    """Rescan bundled and custom skill files."""
    return {"loaded": await _service(context).reload()}


@router.get("/{skill_id}")
async def get_skill(
    skill_id: str,
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Return one skill with its full instructions."""
    entry = _service(context).get(skill_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="skill not found")
    return _response(entry)


@router.post("")
async def create_skill(
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Create and register a custom skill below the configured runtime root."""
    skill_id = payload.get("id")
    frontmatter = payload.get("frontmatter")
    body = payload.get("instructions")
    if (
        not isinstance(skill_id, str)
        or not isinstance(frontmatter, dict)
        or not isinstance(body, str)
    ):
        raise HTTPException(
            status_code=400, detail="id, frontmatter, and instructions are required"
        )
    try:
        entry = await _service(context).write_custom_skill(skill_id, frontmatter, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _response(entry)


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: str,
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, str]:
    """Delete a custom skill; bundled skills remain immutable."""
    try:
        deleted = await _service(context).delete_custom_skill(skill_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="custom skill not found")
    return {"status": "deleted"}


def _service(context: ServiceContext) -> SkillService:
    if context.skill_service is None:
        raise HTTPException(status_code=503, detail="skill service unavailable")
    return context.skill_service


def _response(entry: SkillEntry) -> dict[str, object]:
    return entry.model_dump(mode="json")
