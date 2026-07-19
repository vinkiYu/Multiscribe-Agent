"""Constant-time API-key checks for MCP transports."""

from __future__ import annotations

import hmac
import os

from multiscribe_agent.config import SystemSettings
from multiscribe_agent.mcp.types import MCPAuthError


def get_required_api_key(settings: SystemSettings) -> str:
    """Resolve and require the MCP key without logging its value."""
    key = os.getenv("MCP_API_KEY", "") or settings.mcp_api_key
    if not key:
        raise MCPAuthError("MCP_API_KEY is required for MCP server")
    return key


def verify_api_key(provided: str, expected: str) -> bool:
    """Compare MCP API keys in constant time."""
    return hmac.compare_digest(provided, expected)
