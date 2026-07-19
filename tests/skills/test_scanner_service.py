"""Scanner, registry, and custom override service tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from multiscribe_agent.skills.frontmatter_parser import parse_frontmatter
from multiscribe_agent.skills.scanner import SkillScanner
from multiscribe_agent.skills.service import SkillService


def _write_skill(root: Path, skill_id: str, name: str, body: str = "Body") -> None:
    """Create one minimally valid skill document for scanner tests."""
    directory = root / skill_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: description\nbins: []\n---\n\n{body}\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_scanner_recursively_discovers_skill_documents(tmp_path: Path) -> None:
    """Nested skill directories retain their root-relative stable id."""
    _write_skill(tmp_path, "nested/example", "Nested")
    entries = await SkillScanner(parse_frontmatter).scan_directory(tmp_path, is_builtin=True)
    assert [(entry.id, entry.is_builtin) for entry in entries] == [("nested/example", True)]


@pytest.mark.asyncio
async def test_load_all_allows_custom_skill_to_override_builtin(
    skill_service: SkillService, skill_roots: tuple[Path, Path]
) -> None:
    """Custom documents replace same-id bundled instructions during one load."""
    builtin_root, custom_root = skill_roots
    _write_skill(builtin_root, "digest", "Builtin", "Builtin instructions")
    _write_skill(custom_root, "digest", "Custom", "Custom instructions")
    assert await skill_service.load_all() == 1
    loaded = skill_service.get("digest")
    assert loaded is not None
    assert loaded.name == "Custom"
    assert loaded.is_builtin is False


@pytest.mark.asyncio
async def test_write_and_delete_custom_skill_restores_builtin(
    skill_service: SkillService, skill_roots: tuple[Path, Path]
) -> None:
    """Deleting a custom override reactivates the bundled entry."""
    builtin_root, _ = skill_roots
    _write_skill(builtin_root, "digest", "Builtin")
    await skill_service.load_all()
    created = await skill_service.write_custom_skill(
        "digest", {"name": "Custom", "description": "desc", "bins": []}, "Custom body"
    )
    assert created.is_builtin is False
    assert await skill_service.delete_custom_skill("digest") is True
    restored = skill_service.get("digest")
    assert restored is not None
    assert restored.name == "Builtin"


@pytest.mark.asyncio
async def test_custom_skill_rejects_path_traversal(skill_service: SkillService) -> None:
    """Skill identifiers cannot escape the configured custom root."""
    with pytest.raises(ValueError, match="lowercase"):
        await skill_service.write_custom_skill(
            "../escape", {"name": "Bad", "description": "bad", "bins": []}, "Body"
        )
