from __future__ import annotations

import pytest

from multiscribe_agent.config import SystemSettings
from multiscribe_agent.core.adapter_health import AdapterHealthRepository
from multiscribe_agent.infra.db import init_db


def test_adapter_health_settings_accept_prefixed_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The threshold and alert target settings support the runtime env prefix."""
    monkeypatch.setenv("MULTISCRIBE_ADAPTER_HEALTH_FAILURE_THRESHOLD", "5")
    monkeypatch.setenv("MULTISCRIBE_ADAPTER_HEALTH_ALERT_TARGETS", "feishu_bot,wecom_bot")

    settings = SystemSettings(_env_file=None)

    assert settings.adapter_health_failure_threshold == 5
    assert settings.adapter_health_alert_targets == "feishu_bot,wecom_bot"


@pytest.mark.asyncio
async def test_adapter_health_schema_and_success_reset() -> None:
    """Health rows persist the required fields and successful runs reset failures."""
    database = await init_db(":memory:")
    try:
        columns = await database.fetchall("PRAGMA table_info(adapter_health)")
        assert {str(column["name"]) for column in columns} == {
            "adapter_id",
            "consecutive_failures",
            "disabled",
            "last_status",
            "last_error",
            "last_run_at",
            "updated_at",
        }
        repository = AdapterHealthRepository(failure_threshold=3)
        await repository.record_result(database, adapter_id="rss", success=False, error="temporary")
        health = await repository.record_result(database, adapter_id="rss", success=True)
        assert health.consecutive_failures == 0
        assert health.last_status == "success"
        assert health.last_error is None
        assert (await repository.list_disabled(database)) == set()
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_adapter_health_disables_at_threshold_and_only_alerts_once() -> None:
    """The threshold crossing is marked once and later failures stay disabled."""
    database = await init_db(":memory:")
    try:
        repository = AdapterHealthRepository(failure_threshold=3)
        first = await repository.record_result(
            database, adapter_id="rss", success=False, error="one"
        )
        second = await repository.record_result(
            database, adapter_id="rss", success=False, error="two"
        )
        third = await repository.record_result(
            database, adapter_id="rss", success=False, error="x" * 300
        )
        fourth = await repository.record_result(
            database, adapter_id="rss", success=False, error="four"
        )

        assert first.just_disabled is False
        assert second.just_disabled is False
        assert third.just_disabled is True
        assert fourth.just_disabled is False
        assert third.disabled is True
        assert third.consecutive_failures == 3
        assert third.last_error is not None
        assert len(third.last_error) == 200
        assert await repository.list_disabled(database) == {"rss"}

        await repository.set_disabled(database, adapter_id="rss", disabled=False)
        enabled = await repository.get(database, adapter_id="rss")
        assert enabled is not None
        assert enabled.disabled is False
        assert enabled.consecutive_failures == 0
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_adapter_health_manual_disable_creates_queryable_row() -> None:
    """Operators can disable an adapter before its first scheduled run."""
    database = await init_db(":memory:")
    try:
        repository = AdapterHealthRepository()
        await repository.set_disabled(database, adapter_id="new-source", disabled=True)
        health = await repository.get(database, adapter_id="new-source")
        assert health is not None
        assert health.disabled is True
        assert health.last_status == "unknown"
    finally:
        await database.close()
