"""Optional subprocess isolation for untrusted third-party plugins."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SandboxConfig:
    """Child-process execution limits and entrypoint."""

    plugin_path: Path
    timeout_seconds: float = 30.0
    memory_limit_mb: int = 256


class SandboxError(RuntimeError):
    """Raised when a sandboxed plugin fails or returns an invalid response."""


class SandboxedPluginExecutor:
    """Invoke a plugin using a bounded stdin/stdout JSON protocol."""

    def __init__(self, config: SandboxConfig) -> None:
        if config.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._config = config

    async def execute(self, method: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke one plugin method and decode its JSON object response."""
        payload = json.dumps({"method": method, "arguments": arguments}, ensure_ascii=False)
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(self._config.plugin_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise SandboxError(f"failed to spawn plugin: {type(exc).__name__}") from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(payload.encode("utf-8")),
                timeout=self._config.timeout_seconds,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise SandboxError(f"plugin timed out after {self._config.timeout_seconds}s") from None

        if process.returncode != 0:
            error = stderr.decode("utf-8", errors="replace")[:500]
            raise SandboxError(f"plugin exited {process.returncode}: {error}")
        try:
            result = json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SandboxError(f"plugin returned invalid JSON: {exc.msg}") from exc
        if not isinstance(result, dict):
            raise SandboxError("plugin must return a JSON object")
        return result
