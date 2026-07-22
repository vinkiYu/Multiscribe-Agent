"""Optional subprocess isolation for untrusted third-party plugins."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SandboxConfig:
    """Child-process execution limits and entrypoint."""

    plugin_path: Path
    timeout_seconds: float = 30.0
    memory_limit_mb: int = 256
    max_output_bytes: int = 1_000_000
    require_resource_limits: bool = False


class SandboxError(RuntimeError):
    """Raised when a sandboxed plugin fails or returns an invalid response."""


class SandboxedPluginExecutor:
    """Invoke a plugin using a bounded stdin/stdout JSON protocol."""

    def __init__(self, config: SandboxConfig) -> None:
        if config.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if config.memory_limit_mb <= 0:
            raise ValueError("memory_limit_mb must be positive")
        if config.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
        plugin_path = config.plugin_path.resolve()
        if not plugin_path.is_file():
            raise ValueError("plugin_path must be an existing file")
        if config.require_resource_limits and os.name == "nt":
            raise ValueError("strong plugin resource limits are unavailable on Windows")
        self._config = SandboxConfig(
            plugin_path=plugin_path,
            timeout_seconds=config.timeout_seconds,
            memory_limit_mb=config.memory_limit_mb,
            max_output_bytes=config.max_output_bytes,
            require_resource_limits=config.require_resource_limits,
        )

    async def execute(self, method: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke one plugin method and decode its JSON object response."""
        payload = json.dumps({"method": method, "arguments": arguments}, ensure_ascii=False)
        try:
            process = await self._spawn()
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
            error = stderr[:500].decode("utf-8", errors="replace")
            raise SandboxError(f"plugin exited {process.returncode}: {error}")
        if len(stdout) > self._config.max_output_bytes:
            raise SandboxError(f"plugin output exceeded {self._config.max_output_bytes} bytes")
        try:
            result = json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SandboxError(f"plugin returned invalid JSON: {exc.msg}") from exc
        if not isinstance(result, dict):
            raise SandboxError("plugin must return a JSON object")
        return result

    @staticmethod
    def _sanitized_environment() -> dict[str, str]:
        """Avoid leaking application API keys and webhooks into plugin processes."""
        allowed = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "LANG")
        environment = {key: os.environ[key] for key in allowed if key in os.environ}
        environment["PYTHONUTF8"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return environment

    async def _spawn(self) -> asyncio.subprocess.Process:
        """Spawn with explicit platform options so limits remain type-safe."""
        if os.name == "nt":
            return await asyncio.create_subprocess_exec(
                sys.executable,
                str(self._config.plugin_path),
                cwd=str(self._config.plugin_path.parent),
                env=self._sanitized_environment(),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        return await asyncio.create_subprocess_exec(
            sys.executable,
            str(self._config.plugin_path),
            cwd=str(self._config.plugin_path.parent),
            env=self._sanitized_environment(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=self._posix_preexec(),
            start_new_session=True,
        )

    def _posix_preexec(self) -> Callable[[], None]:
        memory_bytes = self._config.memory_limit_mb * 1024 * 1024
        cpu_seconds = max(1, int(self._config.timeout_seconds) + 1)

        def set_limits() -> None:
            resource = importlib.import_module("resource")
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))

        return set_limits
