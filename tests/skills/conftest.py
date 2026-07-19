"""Skill test helpers with isolated filesystem roots."""

from __future__ import annotations

from pathlib import Path

import pytest

from multiscribe_agent.skills.frontmatter_parser import parse_frontmatter
from multiscribe_agent.skills.registry import SkillRegistry
from multiscribe_agent.skills.scanner import SkillScanner
from multiscribe_agent.skills.service import SkillService


@pytest.fixture
def skill_roots(tmp_path: Path) -> tuple[Path, Path]:
    """Provide independent bundled and custom skill roots."""
    return tmp_path / "builtin", tmp_path / "custom"


@pytest.fixture
def skill_service(skill_roots: tuple[Path, Path]) -> SkillService:
    """Provide a fresh service with an isolated registry and parser."""
    builtin_root, custom_root = skill_roots
    return SkillService(SkillRegistry(), SkillScanner(parse_frontmatter), builtin_root, custom_root)
