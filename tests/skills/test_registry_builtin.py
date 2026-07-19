"""Registry singleton and loader coverage."""

from __future__ import annotations

import pytest

from multiscribe_agent.domain.models import SkillEntry, SkillFrontmatter
from multiscribe_agent.skills.builtin_loader import load_builtin_skills
from multiscribe_agent.skills.registry import SkillRegistry
from multiscribe_agent.skills.service import SkillService


def test_registry_bulk_load_replaces_and_sorts_entries() -> None:
    """Fresh scans replace stale entries and keep predictable output order."""
    registry = SkillRegistry()
    first = SkillEntry(
        id="b",
        name="B",
        description="B",
        instructions="B",
        is_builtin=True,
        frontmatter=SkillFrontmatter(name="B", description="B"),
    )
    second = first.model_copy(update={"id": "a", "name": "A"})
    registry.bulk_load([first, second])
    assert [entry.id for entry in registry.list()] == ["a", "b"]
    registry.bulk_load([first])
    assert [entry.id for entry in registry.list()] == ["b"]


@pytest.mark.asyncio
async def test_builtin_loader_delegates_to_service(skill_service: SkillService) -> None:
    """The bootstrap helper loads the service's configured roots."""
    assert await load_builtin_skills(skill_service) == 0
