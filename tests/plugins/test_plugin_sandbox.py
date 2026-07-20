"""Tests for subprocess-isolated plugin invocation."""

from __future__ import annotations

import textwrap

import pytest

from multiscribe_agent.plugins.sandbox import SandboxConfig, SandboxedPluginExecutor


@pytest.mark.asyncio
async def test_sandbox_executes_json_protocol_plugin(tmp_path) -> None:
    """A child plugin receives method/arguments and returns a JSON object."""
    plugin = tmp_path / "plugin.py"
    plugin.write_text(
        textwrap.dedent(
            """
            import json, sys
            request = json.loads(sys.stdin.read())
            print(json.dumps({
                "method": request["method"],
                "value": request["arguments"]["value"] * 2,
            }))
            """
        ),
        encoding="utf-8",
    )
    executor = SandboxedPluginExecutor(SandboxConfig(plugin, timeout_seconds=2))

    assert await executor.execute("double", {"value": 3}) == {"method": "double", "value": 6}
