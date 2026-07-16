"""Registry isolation fixtures for plugin-system tests."""

from __future__ import annotations

import pytest

from multiscribe_agent.plugins.registry import (
    AdapterRegistry,
    PublisherRegistry,
    StorageRegistry,
    ToolRegistry,
)


@pytest.fixture(autouse=True)
def clear_plugin_registries() -> None:
    """Clear singleton contents before and after every plugin test."""
    registries = (
        AdapterRegistry.get_instance(),
        PublisherRegistry.get_instance(),
        StorageRegistry.get_instance(),
        ToolRegistry.get_instance(),
    )
    for registry in registries:
        registry.clear()
    yield
    for registry in registries:
        registry.clear()
