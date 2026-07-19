"""Skill business operations and safe custom-directory management."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from multiscribe_agent.domain.models import SkillEntry
from multiscribe_agent.skills.frontmatter_parser import parse_frontmatter
from multiscribe_agent.skills.registry import SkillRegistry
from multiscribe_agent.skills.scanner import SkillScanner

_SKILL_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class SkillService:
    """Load, list, create, delete, and reload builtin or custom skills."""

    def __init__(
        self, registry: SkillRegistry, scanner: SkillScanner, builtin_root: Path, custom_root: Path
    ) -> None:
        """Bind registry and explicitly injectable directory roots."""
        self._registry = registry
        self._scanner = scanner
        self._builtin_root = builtin_root
        self._custom_root = custom_root

    async def load_all(self) -> int:
        """Scan both roots, letting custom ids replace bundled ids."""
        builtin, custom = await asyncio.gather(
            self._scanner.scan_directory(self._builtin_root, is_builtin=True),
            self._scanner.scan_directory(self._custom_root, is_builtin=False),
        )
        combined = {entry.id: entry for entry in builtin}
        combined.update({entry.id: entry for entry in custom})
        self._registry.bulk_load(list(combined.values()))
        return len(combined)

    def list(self) -> list[SkillEntry]:
        """List loaded skills in stable order."""
        return self._registry.list()

    def get(self, skill_id: str) -> SkillEntry | None:
        """Return one skill, or None when not loaded."""
        try:
            return self._registry.get(skill_id)
        except KeyError:
            return None

    async def reload(self) -> int:
        """Clear and rescan all configured skill roots."""
        self._registry.clear()
        return await self.load_all()

    async def write_custom_skill(
        self, skill_id: str, frontmatter: dict[str, object], body: str
    ) -> SkillEntry:
        """Create one validated custom SKILL.md and register it."""
        _validate_skill_id(skill_id)
        text = _render_skill(frontmatter, body)
        parsed, instructions = parse_frontmatter(text)
        target = self._custom_root / skill_id / "SKILL.md"
        await asyncio.to_thread(_write_text, target, text)
        entry = SkillEntry(
            id=skill_id,
            name=parsed.name,
            description=parsed.description,
            instructions=instructions,
            is_builtin=False,
            frontmatter=parsed,
            dir_path=str(target.parent),
            files=[target.name],
        )
        self._registry.register(entry)
        return entry

    async def delete_custom_skill(self, skill_id: str) -> bool:
        """Remove a custom file while refusing bundled-only deletion."""
        _validate_skill_id(skill_id)
        target = self._custom_root / skill_id / "SKILL.md"
        if not target.is_file():
            return False
        await asyncio.to_thread(target.unlink)
        await asyncio.to_thread(_remove_empty_parent, target.parent)
        builtin_entries = await self._scanner.scan_directory(self._builtin_root, is_builtin=True)
        replacement = next((entry for entry in builtin_entries if entry.id == skill_id), None)
        if replacement is None:
            self._registry.unregister(skill_id)
        else:
            self._registry.register(replacement)
        return True


def _validate_skill_id(skill_id: str) -> None:
    """Reject traversal and non-portable custom skill identifiers."""
    if not _SKILL_ID.fullmatch(skill_id):
        raise ValueError("skill_id must be lowercase letters, digits, and hyphens")


def _render_skill(frontmatter: dict[str, object], body: str) -> str:
    """Serialize the intentionally small frontmatter schema."""
    name = frontmatter.get("name")
    description = frontmatter.get("description")
    bins = frontmatter.get("bins", [])
    if not isinstance(name, str) or not isinstance(description, str):
        raise ValueError("frontmatter name and description must be strings")
    if not isinstance(bins, list) or not all(isinstance(item, str) for item in bins):
        raise ValueError("frontmatter bins must be a string list")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("skill body must be a non-empty string")
    quoted_bins = ", ".join(repr(item) for item in bins)
    return (
        f"---\nname: {name!r}\ndescription: {description!r}\n"
        f"bins: [{quoted_bins}]\n---\n\n{body.strip()}\n"
    )


def _write_text(path: Path, text: str) -> None:
    """Create parent directories and write UTF-8 text synchronously."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _remove_empty_parent(path: Path) -> None:
    """Remove the direct custom-skill directory only when now empty."""
    try:
        path.rmdir()
    except OSError:
        return
