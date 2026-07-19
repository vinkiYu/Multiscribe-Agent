"""MCP tools that list configured source and publisher plugins."""

from __future__ import annotations

from multiscribe_agent.config import SystemSettings
from multiscribe_agent.plugins.registry import AdapterRegistry, PublisherRegistry


async def list_sources(payload: dict[str, object], settings: SystemSettings) -> dict[str, object]:
    """List discovered adapters with configured enabled flags."""
    del payload
    enabled = {item.id: item.enabled for item in settings.adapters}
    return {
        "sources": [
            {"id": item.id, "type": item.name, "enabled": enabled.get(item.id, False)}
            for item in AdapterRegistry.get_instance().list_metadata()
        ]
    }


async def list_publishers(
    payload: dict[str, object], settings: SystemSettings
) -> dict[str, object]:
    """List discovered publishers with configured enabled flags."""
    del payload
    enabled = {item.id: item.enabled for item in settings.publishers}
    return {
        "publishers": [
            {"id": item.id, "type": item.name, "enabled": enabled.get(item.id, False)}
            for item in PublisherRegistry.get_instance().list_metadata()
        ]
    }
