"""Bundled-skill loading helper."""

from __future__ import annotations

from multiscribe_agent.skills.service import SkillService


async def load_builtin_skills(service: SkillService) -> int:
    """Load bundled and custom skill roots into the registry."""
    return await service.load_all()
