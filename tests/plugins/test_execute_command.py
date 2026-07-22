"""Security and process behavior tests for ExecuteCommandTool."""

from __future__ import annotations

from pathlib import Path

import pytest

from multiscribe_agent.core.errors import ToolExecutionError
from multiscribe_agent.plugins.builtin.tools.execute_command import (
    OUTPUT_LIMIT,
    ExecuteCommandTool,
)


@pytest.mark.asyncio
async def test_allowlisted_read_only_git_command_executes() -> None:
    """A read-only git command executes without a shell."""
    result = await ExecuteCommandTool(Path.cwd()).handler({"command": "git status --short"})

    assert isinstance(result, dict)
    assert result["returncode"] == 0
    assert isinstance(result["stdout"], str)


@pytest.mark.asyncio
async def test_blocked_and_chained_commands_are_rejected() -> None:
    """Blacklist and shell-operator checks prevent direct and chained bypasses."""
    tool = ExecuteCommandTool()
    with pytest.raises(ToolExecutionError, match="blocked command: rm"):
        await tool.handler({"command": "rm file.txt"})
    with pytest.raises(ToolExecutionError, match="shell operators are not allowed"):
        await tool.handler({"command": "echo safe && rm file.txt"})
    with pytest.raises(ToolExecutionError, match="command is not allowed"):
        await tool.handler({"command": "curl https://example.test"})
    with pytest.raises(ToolExecutionError, match="command is not allowed"):
        await tool.handler({"command": "python -c print(1)"})
    with pytest.raises(ToolExecutionError, match="git subcommand is not allowed"):
        await tool.handler({"command": "git push"})


@pytest.mark.asyncio
async def test_invalid_working_directory_is_rejected() -> None:
    """A missing cwd fails before a subprocess is started."""
    with pytest.raises(ToolExecutionError, match="cwd must be an existing directory"):
        await ExecuteCommandTool().handler(
            {"command": "git status", "cwd": "definitely-missing-directory"}
        )


@pytest.mark.asyncio
async def test_command_timeout_is_reported() -> None:
    """Timeout values outside the declared safety boundary are rejected."""
    with pytest.raises(ToolExecutionError, match="timeout must be between"):
        await ExecuteCommandTool().handler({"command": "git status", "timeout": 121})


@pytest.mark.asyncio
async def test_command_output_is_truncated() -> None:
    """The deterministic truncation helper caps large process output."""
    output = ExecuteCommandTool._truncate("x" * (OUTPUT_LIMIT + 100))
    assert len(output) < OUTPUT_LIMIT + 200
    assert "[output truncated: original_chars=" in output


@pytest.mark.asyncio
async def test_working_directory_cannot_escape_workspace(tmp_path) -> None:
    """An existing directory outside the configured root is rejected."""
    root = tmp_path / "workspace"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    with pytest.raises(ToolExecutionError, match="configured workspace"):
        await ExecuteCommandTool(root).handler({"command": "git status", "cwd": str(outside)})
