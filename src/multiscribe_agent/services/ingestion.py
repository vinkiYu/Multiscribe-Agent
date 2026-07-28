"""Coordinate adapter ingestion with normalized content and task-log repositories."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from time import perf_counter

import structlog

from multiscribe_agent.core.adapter_health import AdapterHealth, AdapterHealthRepository
from multiscribe_agent.domain.models import TaskLog
from multiscribe_agent.domain.ports import (
    SourceDataRepository as SourceDataRepositoryPort,
)
from multiscribe_agent.domain.ports import TaskLogRepository as TaskLogRepositoryPort
from multiscribe_agent.infra.db import Database
from multiscribe_agent.plugins.base import BaseAdapter
from multiscribe_agent.plugins.registry import AdapterRegistry
from multiscribe_agent.services.adapter_health_alerter import AdapterHealthAlerter

log = structlog.get_logger(__name__)


class IngestionService:
    """Run source adapters and persist normalized results with lifecycle logging."""

    def __init__(
        self,
        adapter_registry: AdapterRegistry,
        source_data_repo: SourceDataRepositoryPort,
        task_log_repo: TaskLogRepositoryPort,
        runtime_adapters: Mapping[str, BaseAdapter] | None = None,
        *,
        db: Database | None = None,
        health_repo: AdapterHealthRepository | None = None,
        alerter: AdapterHealthAlerter | None = None,
    ) -> None:
        """Create a service from plugin and repository boundaries."""
        self._adapter_registry = adapter_registry
        self._source_data_repo = source_data_repo
        self._task_log_repo = task_log_repo
        self._runtime_adapters = dict(runtime_adapters or {})
        self._db = db
        self._health_repo = health_repo
        self._health_alerter = alerter

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
            adapter = self._runtime_adapters.get(adapter_id)
            if adapter is None:
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
            health = await self._record_health(adapter_id, success=False, error=str(exc))
            if health is not None and health.just_disabled:
                await self._alert_disabled(adapter_id, health)
            return 0

        await self._task_log_repo.update(
            log_id,
            status="success",
            end_time=datetime.now(UTC).isoformat(),
            duration_ms=self._duration_ms(started),
            result_count=inserted,
            message=None,
        )
        await self._record_health(adapter_id, success=True)
        return inserted

    async def run_all(
        self,
        adapter_configs: list[dict[str, object]],
        task_log_id: str | None = None,
        *,
        max_concurrency: int = 4,
    ) -> dict[str, int]:
        """Run enabled adapter configurations with bounded cross-adapter concurrency."""
        tasks: list[tuple[str, dict[str, object]]] = []
        results: dict[str, int] = {}
        disabled = await self._disabled_adapters()
        for adapter_config in adapter_configs:
            if adapter_config.get("enabled") is False:
                continue
            adapter_id = self._adapter_id(adapter_config)
            if adapter_id is None:
                log.warning("ingestion_config_skipped", reason="missing_adapter_id")
                continue
            if adapter_id in disabled:
                log.info("ingestion_adapter_health_disabled", adapter_id=adapter_id)
                results[adapter_id] = 0
                continue
            config_value = adapter_config.get("config", adapter_config)
            if not isinstance(config_value, Mapping):
                log.warning(
                    "ingestion_config_skipped", adapter_id=adapter_id, reason="invalid_config"
                )
                results[adapter_id] = 0
                continue
            tasks.append((adapter_id, dict(config_value)))

        semaphore = asyncio.Semaphore(max(1, max_concurrency))

        async def _bounded(adapter_id: str, config: dict[str, object]) -> tuple[str, int]:
            async with semaphore:
                return adapter_id, await self.run_single(
                    adapter_id,
                    config,
                    task_log_id=task_log_id,
                )

        outcomes = await asyncio.gather(
            *(_bounded(adapter_id, config) for adapter_id, config in tasks),
            return_exceptions=True,
        )
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                log.warning(
                    "ingestion_concurrent_unexpected",
                    error_type=type(outcome).__name__,
                )
                continue
            adapter_id, count = outcome
            results[adapter_id] = count
        return results

    async def _record_health(
        self,
        adapter_id: str,
        *,
        success: bool,
        error: str | None = None,
    ) -> AdapterHealth | None:
        """Persist a health result while keeping health failures out of ingestion."""
        if self._db is None or self._health_repo is None:
            return None
        try:
            return await self._health_repo.record_result(
                self._db,
                adapter_id=adapter_id,
                success=success,
                error=error,
            )
        except Exception as exc:  # Health telemetry must never break the source path.
            log.warning(
                "ingestion_adapter_health_record_failed",
                adapter_id=adapter_id,
                error_type=type(exc).__name__,
            )
            return None

    async def _alert_disabled(self, adapter_id: str, health: AdapterHealth) -> None:
        """Send the threshold alert without affecting the current adapter result."""
        if self._health_alerter is None:
            return
        try:
            await self._health_alerter.alert_disabled(adapter_id, health)
        except Exception as exc:  # Alert delivery is an independent best-effort side effect.
            log.warning(
                "ingestion_adapter_health_alert_failed",
                adapter_id=adapter_id,
                error_type=type(exc).__name__,
            )

    async def _disabled_adapters(self) -> set[str]:
        """Load the persisted disabled set, degrading to an empty set on health DB errors."""
        if self._db is None or self._health_repo is None:
            return set()
        try:
            return await self._health_repo.list_disabled(self._db)
        except Exception as exc:  # Health lookup must not disable the whole ingestion run.
            log.warning("ingestion_adapter_health_lookup_failed", error_type=type(exc).__name__)
            return set()

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
