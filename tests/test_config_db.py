"""Tests for ConfigService persistence through the KV repository."""

from __future__ import annotations

from multiscribe_agent.config import ConfigService
from multiscribe_agent.infra.repositories.kv import KvRepository
from tests.db import init_test_database


async def test_config_service_persists_and_loads_kv_overrides() -> None:
    """Saved settings overrides round-trip through the configured KV repository."""
    db = await init_test_database()
    try:
        service = ConfigService(KvRepository(db))
        await service.save_settings(
            {
                "log_level": "WARNING",
                "selection_fetch_days": 5,
                "closed_plugins": ["rss"],
            },
        )

        settings = await service.get_settings_with_overrides()

        assert settings.log_level == "WARNING"
        assert settings.selection_fetch_days == 5
        assert settings.closed_plugins == ["rss"]
    finally:
        await db.close()
