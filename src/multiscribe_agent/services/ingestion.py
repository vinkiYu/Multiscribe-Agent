"""Coordinate adapter ingestion with normalized content and task-log repositories."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from time import perf_counter

import structlog

from multiscribe_agent.domain.models import TaskLog
from multiscribe_agent.domain.ports import (
    SourceDataRepository as SourceDataRepositoryPort,
)
from multiscribe_agent.domain.ports import TaskLogRepository as TaskLogRepositoryPort
from multiscribe_agent.plugins.registry import AdapterRegistry

log = structlog.get_logger(__name__)


class IngestionService:
    """Run source adapters and persist normalized results with lifecycle logging."""

    def __init__(
        self,
        adapter_registry: AdapterRegistry,
        source_data_repo: SourceDataRepositoryPort,
        task_log_repo: TaskLogRepositoryPort,
    ) -> None:
        """Create a service from plugin and repository boundaries."""
        self._adapter_registry = adapter_registry
        self._source_data_repo = source_data_repo
        self._task_log_repo = task_log_repo

    async def run_single(
        self,
        adapter_id: str,
        config: dict[str, object],
        task_log_id: str | None = None,
    ) -> int:
        """Run one adapter, save unique items, and complete its task log."""
        started_at = datetime.now(UTC).isoformat()
        started = perf_counter()
        log_id = task_log_id or await self._task_log_repo.create(
            TaskLog(
                task_id=adapter_id,
                task_name=f"Ingest {adapter_id}",
                start_time=started_at,
                status="running",
            )
        )
        if task_log_id is not None:
            await self._task_log_repo.update(log_id, status="running", start_time=started_at)
        try:
            adapter_class = self._adapter_registry.get(adapter_id)
            adapter = adapter_class()
            items = await adapter.fetch_and_transform(config)
            inserted = await self._source_data_repo.save_batch(items, adapter_id)
        except Exception as exc:  # Individual adapters must not stop run_all.
            duration = self._duration_ms(started)
            log.warning(
                "ingestion_adapter_failed",
                adapter_id=adapter_id,
                error_type=type(exc).__name__,
            )
            await self._task_log_repo.update(
                log_id,
                status="error",
                end_time=datetime.now(UTC).isoformat(),
                duration_ms=duration,
                result_count=0,
                message=f"{type(exc).__name__}: {exc}",
            )
            return 0

        await self._task_log_repo.update(
            log_id,
            status="success",
            end_time=datetime.now(UTC).isoformat(),
            duration_ms=self._duration_ms(started),
            result_count=inserted,
            message=None,
        )
        return inserted

    async def run_all(
        self, adapter_configs: list[dict[str, object]], task_log_id: str | None = None
    ) -> dict[str, int]:
        """Run enabled adapter configurations independently and return per-adapter counts."""
        results: dict[str, int] = {}
        for adapter_config in adapter_configs:
            if adapter_config.get("enabled") is False:
                continue
            adapter_id = self._adapter_id(adapter_config)
            if adapter_id is None:
                log.warning("ingestion_config_skipped", reason="missing_adapter_id")
                continue
            config_value = adapter_config.get("config", adapter_config)
            if not isinstance(config_value, Mapping):
                log.warning(
                    "ingestion_config_skipped", adapter_id=adapter_id, reason="invalid_config"
                )
                results[adapter_id] = 0
                continue
            results[adapter_id] = await self.run_single(
                adapter_id,
                dict(config_value),
                task_log_id=task_log_id,
            )
        return results

    @staticmethod
    def _adapter_id(config: Mapping[str, object]) -> str | None:
        for key in ("adapter_id", "id"):
            value = config.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _duration_ms(started: float) -> int:
        return round((perf_counter() - started) * 1000)
