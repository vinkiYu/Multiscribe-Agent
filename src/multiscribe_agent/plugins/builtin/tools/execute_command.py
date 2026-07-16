"""Restricted local command execution tool used as a plugin-system example."""

from __future__ import annotations

import asyncio
import os
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from multiscribe_agent.core.errors import ToolExecutionError
from multiscribe_agent.domain.models import ConfigField, PluginMetadata
from multiscribe_agent.plugins.base import BaseTool

ALLOWED = frozenset({"node", "npm", "npx", "git", "ls", "echo", "python", "pip", "uv"})
BLOCKED = frozenset({"rm", "format", "mkfs", "dd", "shutdown"})
SHELL_OPERATORS = ("&&", "||", ";", "|", "\n", "\r", ">", "<", "`")
DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 120
OUTPUT_LIMIT = 20_000


class ExecuteCommandTool(BaseTool):
    """Execute one allowlisted command with timeout and bounded output."""

    id: ClassVar[str] = "execute_command"
    name: ClassVar[str] = "execute_command"
    description: ClassVar[str] = "Execute one restricted local development command."
    is_builtin: ClassVar[bool] = True
    parameters: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "cwd": {"type": "string"},
            "timeout": {"type": "integer", "minimum": 1, "maximum": MAX_TIMEOUT_SECONDS},
        },
        "required": ["command"],
        "additionalProperties": False,
    }
    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id=id,
        type="tool",
        name="Execute Command",
        description=description,
        icon="terminal",
        config_fields=[
            ConfigField(
                key="approval_required",
                label="Require approval",
                type="boolean",
                default=True,
            )
        ],
        is_builtin=True,
    )

    async def handler(self, args: Mapping[str, object]) -> object:
        """Run one safe command and return stdout, stderr, and exit status.

        Raises:
            ToolExecutionError: If arguments are invalid, the command is unsafe,
                execution times out, or the process cannot be started.
        """
        command = self._required_string(args, "command")
        command_name = self._validate_command(command)
        cwd = await self._optional_cwd(args.get("cwd"))
        timeout = self._timeout(args.get("timeout"))
        if command_name not in ALLOWED:
            raise ToolExecutionError(f"command requires approval: {command_name}")

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise ToolExecutionError(f"unable to start command: {command_name}") from exc
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise ToolExecutionError(f"command timed out after {timeout} seconds") from exc
        return {
            "stdout": self._truncate(stdout.decode(errors="replace")),
            "stderr": self._truncate(stderr.decode(errors="replace")),
            "returncode": process.returncode,
        }

    @staticmethod
    def _validate_command(command: str) -> str:
        if any(operator in command for operator in SHELL_OPERATORS):
            raise ToolExecutionError("shell operators are not allowed")
        try:
            parts = shlex.split(command, posix=os.name != "nt")
        except ValueError as exc:
            raise ToolExecutionError("command has invalid quoting") from exc
        if not parts:
            raise ToolExecutionError("command must not be empty")
        executable = Path(parts[0].strip("\"'")).name.lower()
        for suffix in (".exe", ".cmd", ".bat"):
            if executable.endswith(suffix):
                executable = executable[: -len(suffix)]
                break
        if executable in BLOCKED:
            raise ToolExecutionError(f"blocked command: {executable}")
        return executable

    @staticmethod
    def _required_string(args: Mapping[str, object], key: str) -> str:
        value = args.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ToolExecutionError(f"{key} must be a non-empty string")
        return value.strip()

    @staticmethod
    async def _optional_cwd(value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ToolExecutionError("cwd must be a non-empty string")
        path = Path(value).expanduser()
        if not await asyncio.to_thread(path.is_dir):
            raise ToolExecutionError("cwd must be an existing directory")
        return str(path)

    @staticmethod
    def _timeout(value: object) -> int:
        if value is None:
            return DEFAULT_TIMEOUT_SECONDS
        if not isinstance(value, int) or isinstance(value, bool):
            raise ToolExecutionError("timeout must be an integer")
        if not 1 <= value <= MAX_TIMEOUT_SECONDS:
            raise ToolExecutionError(f"timeout must be between 1 and {MAX_TIMEOUT_SECONDS}")
        return value

    @staticmethod
    def _truncate(output: str) -> str:
        if len(output) <= OUTPUT_LIMIT:
            return output
        return output[:OUTPUT_LIMIT] + f"\n[output truncated: original_chars={len(output)}]"
