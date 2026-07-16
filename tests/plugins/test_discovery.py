"""Tests for import-based plugin discovery and registration."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from multiscribe_agent.plugins.discovery import scan_and_register
from multiscribe_agent.plugins.registry import ToolRegistry


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_scan_registers_metadata_classes_and_skips_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A temporary package proves registration count, skip rules, and idempotency."""
    package = tmp_path / "temporary_plugins"
    _write(package / "__init__.py")
    _write(package / "builtin" / "__init__.py")
    _write(
        package / "builtin" / "good_tool.py",
        """from collections.abc import Mapping
from typing import ClassVar
from multiscribe_agent.domain.models import PluginMetadata
from multiscribe_agent.plugins.base import BaseTool

class TemporaryTool(BaseTool):
    id: ClassVar[str] = "temporary_tool"
    name: ClassVar[str] = "temporary_tool"
    description: ClassVar[str] = "Temporary."
    parameters: ClassVar[dict[str, object]] = {"type": "object"}
    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id=id, type="tool", name="Temporary", description=description
    )
    async def handler(self, args: Mapping[str, object]) -> object:
        return dict(args)
""",
    )
    _write(
        package / "builtin" / "ignored_base.py",
        """from multiscribe_agent.plugins.builtin.tools.execute_command import ExecuteCommandTool
class IgnoredTool(ExecuteCommandTool):
    pass
""",
    )
    _write(package / "builtin" / "plain.py", "class PlainClass:\n    pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()

    first = scan_and_register("temporary_plugins")
    second = scan_and_register("temporary_plugins")

    assert first.registered == ["temporary_plugins.builtin.good_tool.TemporaryTool"]
    assert "temporary_plugins.builtin.ignored_base" in first.skipped
    assert "temporary_plugins.builtin.plain.PlainClass" in first.skipped
    assert second.registered == first.registered
    assert ToolRegistry.get_instance().get_class("temporary_tool").__name__ == "TemporaryTool"
    assert len(ToolRegistry.get_instance().list_metadata()) == 1


def test_default_scan_discovers_builtin_execute_command() -> None:
    """The real builtin package exposes the example tool class without instantiation."""
    result = scan_and_register()

    assert (
        "multiscribe_agent.plugins.builtin.tools.execute_command.ExecuteCommandTool"
        in result.registered
    )
    assert ToolRegistry.get_instance().get_class("execute_command").__name__ == (
        "ExecuteCommandTool"
    )
    with pytest.raises(KeyError):
        ToolRegistry.get_instance().get_tool("execute_command")
