"""Tests for adapter-to-repository ingestion orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from time import perf_counter
from typing import ClassVar

import pytest

from multiscribe_agent.core.adapter_health import AdapterHealth, AdapterHealthRepository
from multiscribe_agent.domain.models import PluginMetadata, TaskLog, UnifiedData
from multiscribe_agent.infra.db import init_db
from multiscribe_agent.plugins.base import BaseAdapter
from multiscribe_agent.plugins.registry import AdapterRegistry
from multiscribe_agent.services.adapter_health_alerter import AdapterHealthAlerter
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


class ControlledAdapter(BaseAdapter):
    """Runtime adapter with controllable delay and concurrency instrumentation."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="controlled", type="adapter", name="Controlled", description="Controlled adapter."
    )

    def __init__(
        self,
        item_id: str,
        tracker: dict[str, int],
        delay: float = 0.0,
        fail: bool = False,
    ) -> None:
        self._item_id = item_id
        self._tracker = tracker
        self._delay = delay
        self._fail = fail

    async def fetch(self, config: Mapping[str, object]) -> object:
        """Sleep while tracking active adapter executions."""
        del config
        self._tracker["calls"] += 1
        self._tracker["running"] += 1
        self._tracker["peak"] = max(self._tracker["peak"], self._tracker["running"])
        try:
            await asyncio.sleep(self._delay)
            if self._fail:
                raise RuntimeError("controlled adapter crash")
            return [item(self._item_id)]
        finally:
            self._tracker["running"] -= 1

    def transform(
        self, raw: object, config: Mapping[str, object] | None = None
    ) -> list[UnifiedData]:
        """Pass through normalized fixture items."""
        del config
        return list(raw) if isinstance(raw, list) else []

    async def fetch_and_transform(self, config: Mapping[str, object]) -> list[UnifiedData]:
        """Allow one fixture to exercise run_single's outer failure boundary."""
        if self._fail:
            await self.fetch(config)
            raise AssertionError("failed controlled adapter unexpectedly returned")
        return await super().fetch_and_transform(config)


class RuntimeAdapter(SuccessAdapter):
    """Adapter instance used to verify dependency-injected runtime adapters."""

    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id="runtime", type="adapter", name="Runtime", description="Runtime adapter."
    )


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


class RecordingAlerter:
    """Capture threshold alerts and optionally fail like a publisher."""

    def __init__(self, fail: bool = False) -> None:
        self.alerts: list[tuple[str, AdapterHealth]] = []
        self.fail = fail

    async def alert_disabled(self, adapter_id: str, health: AdapterHealth) -> None:
        if self.fail:
            raise RuntimeError("alert publisher unavailable")
        self.alerts.append((adapter_id, health))


class RecordingPublisher:
    """Publisher double for the plain-text adapter health alert."""

    received: ClassVar[list[tuple[object, object]]] = []

    async def publish(self, content: object, options: object = None) -> dict[str, object]:
        self.received.append((content, options))
        return {"ok": True}


class PublisherRegistryDouble:
    """Minimal publisher registry boundary accepted by the alerter."""

    def get(self, target: str) -> type[RecordingPublisher]:
        assert target == "feishu_bot"
        return RecordingPublisher


def controlled_service(adapters: dict[str, BaseAdapter]) -> IngestionService:
    """Build an ingestion service with runtime-controlled adapter instances."""
    registry = AdapterRegistry.get_instance()
    registry.clear()
    return IngestionService(
        registry,
        MemorySourceDataRepository(),
        MemoryTaskLogRepository(),
        runtime_adapters=adapters,
    )


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


@pytest.mark.asyncio
async def test_runtime_adapter_instance_overrides_registry_construction() -> None:
    """Adapters requiring runtime dependencies can participate in normal ingestion."""
    RuntimeAdapter.items = [item("runtime-1")]
    registry = AdapterRegistry.get_instance()
    registry.clear()
    source_repo = MemorySourceDataRepository()
    task_repo = MemoryTaskLogRepository()
    service = IngestionService(
        registry,
        source_repo,
        task_repo,
        runtime_adapters={"ai_search": RuntimeAdapter()},
    )

    inserted = await service.run_single("ai_search", {})

    assert inserted == 1
    assert source_repo.saved_batches == [([item("runtime-1")], "ai_search")]


@pytest.mark.asyncio
async def test_run_all_runs_four_slow_adapters_concurrently_by_default() -> None:
    """The default concurrency of four removes cross-adapter serial waiting."""
    tracker = {"calls": 0, "running": 0, "peak": 0}
    service = controlled_service(
        {
            f"slow-{index}": ControlledAdapter(f"slow-{index}", tracker, delay=0.5)
            for index in range(4)
        }
    )

    started = perf_counter()
    results = await service.run_all(
        [{"adapter_id": f"slow-{index}", "config": {}} for index in range(4)]
    )
    elapsed = perf_counter() - started

    assert results == {f"slow-{index}": 1 for index in range(4)}
    assert tracker["peak"] == 4
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_run_all_isolates_one_concurrent_adapter_failure() -> None:
    """A failing adapter returns zero while its successful peer still completes."""
    tracker = {"calls": 0, "running": 0, "peak": 0}
    service = controlled_service(
        {
            "failure": ControlledAdapter("failure-item", tracker, fail=True),
            "success": ControlledAdapter("success-item", tracker),
        }
    )

    results = await service.run_all(
        [
            {"adapter_id": "failure", "config": {}},
            {"adapter_id": "success", "config": {}},
        ]
    )

    task_repo = service._task_log_repo
    assert isinstance(task_repo, MemoryTaskLogRepository)
    assert results == {"failure": 0, "success": 1}
    assert {log.status for log in task_repo.logs.values()} == {"error", "success"}


@pytest.mark.asyncio
async def test_run_all_respects_max_concurrency_semaphore() -> None:
    """A configured limit bounds active adapter work even with more candidates."""
    tracker = {"calls": 0, "running": 0, "peak": 0}
    service = controlled_service(
        {
            f"bounded-{index}": ControlledAdapter(f"bounded-{index}", tracker, delay=0.05)
            for index in range(4)
        }
    )

    results = await service.run_all(
        [{"adapter_id": f"bounded-{index}", "config": {}} for index in range(4)],
        max_concurrency=2,
    )

    assert results == {f"bounded-{index}": 1 for index in range(4)}
    assert tracker["peak"] <= 2


@pytest.mark.asyncio
async def test_run_all_skips_disabled_adapter_before_scheduling() -> None:
    """Disabled configurations do not construct or execute an adapter task."""
    tracker = {"calls": 0, "running": 0, "peak": 0}
    service = controlled_service(
        {
            "disabled": ControlledAdapter("disabled-item", tracker),
            "enabled": ControlledAdapter("enabled-item", tracker),
        }
    )

    results = await service.run_all(
        [
            {"adapter_id": "disabled", "enabled": False, "config": {}},
            {"adapter_id": "enabled", "config": {}},
        ]
    )

    assert results == {"enabled": 1}
    assert tracker["calls"] == 1


@pytest.mark.asyncio
async def test_health_threshold_disables_adapter_and_run_all_skips_it() -> None:
    """Three failures persist a disabled state, alert once, and prevent later callbacks."""
    database = await init_db(":memory:")
    try:
        registry = AdapterRegistry.get_instance()
        registry.clear()
        registry.register("failure", FailingAdapter, FailingAdapter.metadata)
        source_repo = MemorySourceDataRepository()
        task_repo = MemoryTaskLogRepository()
        health_repo = AdapterHealthRepository(failure_threshold=3)
        alerter = RecordingAlerter()
        service = IngestionService(
            registry,
            source_repo,
            task_repo,
            db=database,
            health_repo=health_repo,
            alerter=alerter,  # type: ignore[arg-type]
        )

        for _ in range(3):
            assert await service.run_single("failure", {}) == 0

        health = await health_repo.get(database, adapter_id="failure")
        assert health is not None
        assert health.disabled is True
        assert len(alerter.alerts) == 1
        skipped = await service.run_all([{"adapter_id": "failure", "config": {}}])
        assert skipped == {"failure": 0}
        assert len(task_repo.logs) == 3

        await health_repo.set_disabled(database, adapter_id="failure", disabled=False)
        resumed = await service.run_all([{"adapter_id": "failure", "config": {}}])
        assert resumed == {"failure": 0}
        assert len(task_repo.logs) == 4
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_health_alert_failure_does_not_break_ingestion() -> None:
    """A publisher outage cannot turn the adapter health side effect into a crash."""
    database = await init_db(":memory:")
    try:
        registry = AdapterRegistry.get_instance()
        registry.clear()
        registry.register("failure", FailingAdapter, FailingAdapter.metadata)
        service = IngestionService(
            registry,
            MemorySourceDataRepository(),
            MemoryTaskLogRepository(),
            db=database,
            health_repo=AdapterHealthRepository(failure_threshold=1),
            alerter=RecordingAlerter(fail=True),  # type: ignore[arg-type]
        )

        assert await service.run_single("failure", {}) == 0
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_adapter_health_alerter_publishes_plain_text_without_blocking() -> None:
    """The alert contains operational fields and uses the existing publisher contract."""
    RecordingPublisher.received = []
    alerter = AdapterHealthAlerter(
        ["feishu_bot"],
        {"feishu_bot": {"webhook": "https://example.test/hook"}},
        publisher_registry=PublisherRegistryDouble(),  # type: ignore[arg-type]
    )
    health = AdapterHealth(
        adapter_id="rss",
        consecutive_failures=3,
        disabled=True,
        last_status="error",
        last_error="feed timeout",
        last_run_at="2026-07-29T00:00:00+00:00",
        updated_at="2026-07-29T00:00:00+00:00",
    )

    await alerter.alert_disabled("rss", health)

    assert len(RecordingPublisher.received) == 1
    content, options = RecordingPublisher.received[0]
    assert isinstance(content, str)
    assert "rss" in content
    assert "Consecutive failures: 3" in content
    assert options == {"webhook": "https://example.test/hook"}
