"""Tests for the four abstract plugin contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

import pytest

from multiscribe_agent.domain.models import PluginMetadata, UnifiedData
from multiscribe_agent.plugins.base import (
    BaseAdapter,
    BasePublisher,
    BaseStorageProvider,
    BaseTool,
)

ADAPTER_METADATA = PluginMetadata(
    id="test_adapter",
    type="adapter",
    name="Test adapter",
    description="Test adapter metadata.",
)


class WorkingAdapter(BaseAdapter):
    """Minimal concrete adapter used by template-method tests."""

    metadata: ClassVar[PluginMetadata] = ADAPTER_METADATA

    async def fetch(self, config: Mapping[str, object]) -> object:
        """Return configured raw input."""
        return config.get("raw", [])

    def transform(
        self, raw: object, config: Mapping[str, object] | None = None
    ) -> list[UnifiedData]:
        """Return no domain rows for this contract-only test."""
        del raw, config
        return []


class FailingAdapter(WorkingAdapter):
    """Adapter whose external fetch boundary fails."""

    async def fetch(self, config: Mapping[str, object]) -> object:
        """Raise a deterministic source failure."""
        del config
        raise RuntimeError("fake source failure")


def test_abstract_bases_cannot_be_instantiated() -> None:
    """Each plugin base enforces its required abstract methods."""
    for base_class in (BaseAdapter, BasePublisher, BaseStorageProvider, BaseTool):
        with pytest.raises(TypeError):
            base_class()


def test_incomplete_adapter_subclass_remains_abstract() -> None:
    """Implementing fetch without transform is insufficient."""

    class IncompleteAdapter(BaseAdapter):
        metadata: ClassVar[PluginMetadata] = ADAPTER_METADATA

        async def fetch(self, config: Mapping[str, object]) -> object:
            return config

    with pytest.raises(TypeError):
        IncompleteAdapter()


@pytest.mark.asyncio
async def test_fetch_and_transform_returns_empty_on_adapter_error() -> None:
    """A source failure is isolated as an empty adapter result."""
    assert await FailingAdapter().fetch_and_transform({}) == []


@pytest.mark.asyncio
async def test_default_publisher_item_url_is_none() -> None:
    """Concrete publishers inherit an optional no-URL implementation."""

    class Publisher(BasePublisher):
        metadata: ClassVar[PluginMetadata] = PluginMetadata(
            id="publisher", type="publisher", name="Publisher", description="Test."
        )

        async def publish(
            self, content: object, options: Mapping[str, object] | None = None
        ) -> dict[str, object]:
            del content, options
            return {"status": "ok"}

    assert await Publisher().get_item_url(object()) is None
