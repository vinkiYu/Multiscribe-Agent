"""Asynchronous filesystem scanner for SKILL.md directories."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from multiscribe_agent.domain.models import SkillEntry, SkillFrontmatter


class SkillScanner:
    """Discover ``<id>/SKILL.md`` files beneath one skill root."""

    def __init__(self, parse_frontmatter: Callable[[str], tuple[SkillFrontmatter, str]]) -> None:
        """Configure the parser used to turn SKILL.md text into entries."""
        self._parse_frontmatter = parse_frontmatter

    async def scan_directory(self, root: Path, *, is_builtin: bool = False) -> list[SkillEntry]:
        """Recursively discover and parse every named SKILL.md below root."""
        return await asyncio.to_thread(self._scan_sync, root, is_builtin)

    def _scan_sync(self, root: Path, is_builtin: bool) -> list[SkillEntry]:
        """Perform filesystem traversal off the event loop."""
        if not root.is_dir():
            return []
        entries: list[SkillEntry] = []
        for path in sorted(root.rglob("SKILL.md")):
            if not path.is_file() or path.parent == root:
                continue
            skill_id = path.parent.relative_to(root).as_posix()
            frontmatter, instructions = self._parse_frontmatter(path.read_text(encoding="utf-8"))
            entries.append(
                SkillEntry(
                    id=skill_id,
                    name=frontmatter.name,
                    description=frontmatter.description,
                    instructions=instructions,
                    is_builtin=is_builtin,
                    frontmatter=frontmatter,
                    dir_path=str(path.parent),
                    files=[path.name],
                )
            )
        return entries
