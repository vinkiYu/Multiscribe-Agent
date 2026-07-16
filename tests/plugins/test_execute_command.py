"""Security and process behavior tests for ExecuteCommandTool."""

from __future__ import annotations

import sys

import pytest

from multiscribe_agent.core.errors import ToolExecutionError
from multiscribe_agent.plugins.builtin.tools.execute_command import (
    OUTPUT_LIMIT,
    ExecuteCommandTool,
)


@pytest.mark.asyncio
async def test_allowlisted_python_command_executes() -> None:
    """An allowlisted single command returns bounded process output."""
    result = await ExecuteCommandTool().handler(
        {"command": f'"{sys.executable}" -c "print(\'safe-output\')"'}
    )

    assert isinstance(result, dict)
    assert result["returncode"] == 0
    assert result["stdout"].strip() == "safe-output"
    assert result["stderr"] == ""


@pytest.mark.asyncio
async def test_blocked_and_chained_commands_are_rejected() -> None:
    """Blacklist and shell-operator checks prevent direct and chained bypasses."""
    tool = ExecuteCommandTool()
    with pytest.raises(ToolExecutionError, match="blocked command: rm"):
        await tool.handler({"command": "rm file.txt"})
    with pytest.raises(ToolExecutionError, match="shell operators are not allowed"):
        await tool.handler({"command": "echo safe && rm file.txt"})
    with pytest.raises(ToolExecutionError, match="requires approval"):
        await tool.handler({"command": "curl https://example.test"})


@pytest.mark.asyncio
async def test_invalid_working_directory_is_rejected() -> None:
    """A missing cwd fails before a subprocess is started."""
    with pytest.raises(ToolExecutionError, match="cwd must be an existing directory"):
        await ExecuteCommandTool().handler(
            {"command": "echo safe", "cwd": "definitely-missing-directory"}
        )


@pytest.mark.asyncio
async def test_command_timeout_is_reported() -> None:
    """A long-running allowlisted process is killed and reported as a tool error."""
    command = f'"{sys.executable}" -c "__import__(\'time\').sleep(2)"'

    with pytest.raises(ToolExecutionError, match="timed out after 1 seconds"):
        await ExecuteCommandTool().handler({"command": command, "timeout": 1})


@pytest.mark.asyncio
async def test_command_output_is_truncated() -> None:
    """Large stdout is capped and includes an explicit truncation marker."""
    command = f'"{sys.executable}" -c "print(\'x\'*{OUTPUT_LIMIT + 100})"'

    result = await ExecuteCommandTool().handler({"command": command})

    assert isinstance(result, dict)
    assert len(result["stdout"]) < OUTPUT_LIMIT + 200
    assert "[output truncated: original_chars=" in result["stdout"]
