"""Tests for adapter-to-repository ingestion orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

import pytest

from multiscribe_agent.domain.models import PluginMetadata, TaskLog, UnifiedData
from multiscribe_agent.plugins.base import BaseAdapter
from multiscribe_agent.plugins.registry import AdapterRegistry
from multiscribe_agent.services.ingestion import IngestionService


def item(item_id: str) -> UnifiedData:
    """Build a minimal normalized item for fake adapters."""
    return UnifiedData(
        id=item_id,
        title="Fixture item",
        url=f"https://example.test/{item_id}",
        description="Fixture description",
        published_date="2026-07-16T00:00:00+00:00",
        source="fixture",
        category="test",
    )


class SuccessAdapter(BaseAdapter):
    """Adapter returning items injected through a class-level test value."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="success", type="adapter", name="Success", description="Success adapter."
    )
    items: ClassVar[list[UnifiedData]] = []

    async def fetch(self, config: Mapping[str, object]) -> object:
        del config
        return self.items

    def transform(
        self, raw: object, config: Mapping[str, object] | None = None
    ) -> list[UnifiedData]:
        del config
        return list(raw) if isinstance(raw, list) else []


class FailingAdapter(SuccessAdapter):
    """Adapter that fails outside BaseAdapter's local empty-result policy."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="failure", type="adapter", name="Failure", description="Failure adapter."
    )

    async def fetch_and_transform(self, config: Mapping[str, object]) -> list[UnifiedData]:
        del config
        raise RuntimeError("fake adapter crash")


class MemorySourceDataRepository:
    """In-memory source repository with ID deduplication."""

    def __init__(self) -> None:
        self.ids: set[str] = set()
        self.saved_batches: list[tuple[list[UnifiedData], str]] = []

    async def save_batch(self, items: list[UnifiedData], adapter_name: str) -> int:
        self.saved_batches.append((items, adapter_name))
        new_ids = [entry.id for entry in items if entry.id not in self.ids]
        self.ids.update(new_ids)
        return len(new_ids)


class MemoryTaskLogRepository:
    """In-memory task logs retaining create and update fields for assertions."""

    def __init__(self) -> None:
        self.logs: dict[str, TaskLog] = {}
        self.updates: list[tuple[str, dict[str, object]]] = []
        self._next_id = 1

    async def create(self, log: TaskLog) -> str:
        log_id = str(self._next_id)
        self._next_id += 1
        self.logs[log_id] = log.model_copy(update={"id": log_id})
        return log_id

    async def update(self, log_id: str, **fields: object) -> None:
        self.updates.append((log_id, fields))
        self.logs[log_id] = self.logs[log_id].model_copy(update=fields)

    async def get(self, log_id: str) -> TaskLog | None:
        return self.logs.get(log_id)


@pytest.fixture
def service() -> IngestionService:
    """Provide a service with two registered fake adapter classes."""
    registry = AdapterRegistry.get_instance()
    registry.clear()
    registry.register("success", SuccessAdapter, SuccessAdapter.metadata)
    registry.register("failure", FailingAdapter, FailingAdapter.metadata)
    return IngestionService(registry, MemorySourceDataRepository(), MemoryTaskLogRepository())


@pytest.mark.asyncio
async def test_run_single_persists_and_deduplicates_with_complete_task_log(
    service: IngestionService,
) -> None:
    """Success writes unique source items and marks each task log complete."""
    SuccessAdapter.items = [item("rss-1")]

    first = await service.run_single("success", {})
    second = await service.run_single("success", {})

    source_repo = service._source_data_repo
    task_repo = service._task_log_repo
    assert isinstance(source_repo, MemorySourceDataRepository)
    assert isinstance(task_repo, MemoryTaskLogRepository)
    assert (first, second) == (1, 0)
    assert source_repo.ids == {"rss-1"}
    assert all(log.status == "success" for log in task_repo.logs.values())
    assert all(log.end_time is not None for log in task_repo.logs.values())
    assert [log.result_count for log in task_repo.logs.values()] == [1, 0]


@pytest.mark.asyncio
async def test_run_all_continues_after_adapter_error(service: IngestionService) -> None:
    """A failing adapter records error status without preventing a successful peer."""
    SuccessAdapter.items = [item("rss-2")]

    results = await service.run_all(
        [
            {"adapter_id": "failure", "config": {}},
            {"adapter_id": "success", "config": {}},
        ]
    )

    task_repo = service._task_log_repo
    assert isinstance(task_repo, MemoryTaskLogRepository)
    assert results == {"failure": 0, "success": 1}
    assert [log.status for log in task_repo.logs.values()] == ["error", "success"]
    assert task_repo.logs["1"].result_count == 0
