"""Tests for Plugin API version compatibility enforcement."""

from __future__ import annotations

import pytest

from multiscribe_agent.domain.models import PluginMetadata
from multiscribe_agent.plugins.base import BaseAdapter
from multiscribe_agent.plugins.registry import (
    AdapterRegistry,
    IncompatiblePluginError,
)


class _Adapter(BaseAdapter):
    metadata = PluginMetadata(
        id="versioned-adapter",
        type="adapter",
        name="Versioned",
        description="test",
    )

    async def fetch(self, config):
        del config
        return []

    def transform(self, raw, config=None):
        del raw, config
        return []


def test_plugin_metadata_defaults_to_current_api_version() -> None:
    """Existing plugins remain compatible without declaring the new field."""
    assert _Adapter.metadata.api_version == "1.0"


def test_incompatible_plugin_registration_is_rejected() -> None:
    """A plugin declaring a different API contract cannot enter the registry."""
    metadata = _Adapter.metadata.model_copy(update={"api_version": "2.0"})
    with pytest.raises(IncompatiblePluginError):
        AdapterRegistry().register("bad", _Adapter, metadata)
