"""MCP API-key boundary coverage."""

from __future__ import annotations

import pytest

from multiscribe_agent.config import SystemSettings
from multiscribe_agent.mcp.auth import get_required_api_key, verify_api_key
from multiscribe_agent.mcp.types import MCPAuthError


def test_mcp_key_requires_configuration(monkeypatch) -> None:
    """A server cannot start without an explicit MCP credential."""
    monkeypatch.delenv("MCP_API_KEY", raising=False)
    with pytest.raises(MCPAuthError, match="required"):
        get_required_api_key(SystemSettings(_env_file=None))


def test_mcp_key_reads_environment_and_compares_in_constant_time(monkeypatch) -> None:
    """Environment keys take precedence and reject incorrect values."""
    monkeypatch.setenv("MCP_API_KEY", "test-key")
    key = get_required_api_key(SystemSettings(_env_file=None, mcp_api_key="fallback"))
    assert key == "test-key"
    assert verify_api_key("test-key", key) is True
    assert verify_api_key("wrong", key) is False
