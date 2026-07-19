from pathlib import Path

import pytest

from multiscribe_agent.skills.frontmatter_parser import parse_frontmatter
from multiscribe_agent.skills.scanner import SkillScanner


@pytest.mark.asyncio
async def test_loop_engineering_skill_is_discoverable() -> None:
    entries = await SkillScanner(parse_frontmatter).scan_directory(Path("data/skills"))
    found = {entry.id for entry in entries}
    assert "loop-engineering-patterns" in found
