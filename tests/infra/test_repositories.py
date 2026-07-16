"""Tests for SQLite repository CRUD, safety, and search behavior."""

import pytest

from multiscribe_agent.domain.models import TaskLog, UnifiedData
from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.repositories.api_key import ApiKeyRepository
from multiscribe_agent.infra.repositories.entity_json import EntityJsonRepository
from multiscribe_agent.infra.repositories.kv import KvRepository
from multiscribe_agent.infra.repositories.source_data import SourceDataRepository
from multiscribe_agent.infra.repositories.task_log import TaskLogRepository


def _item(item_id: str, title: str, source: str = "rss") -> UnifiedData:
    return UnifiedData(
        id=item_id,
        title=title,
        url=f"https://example.com/{item_id}",
        description=f"{title} searchable description",
        published_date="2026-07-16",
        ingestion_date="2026-07-16",
        source=source,
        category="news",
        metadata={"ai_summary": f"{title} summary"},
    )


async def test_kv_crud_and_expired_value_is_deleted(db: Database) -> None:
    """KV values round-trip through JSON and expired rows are lazily removed."""
    repository = KvRepository(db)
    await repository.set("settings", {"level": "INFO"})

    assert await repository.get("settings") == {"level": "INFO"}

    await repository.set("expired", "old", ttl_seconds=-1)

    assert await repository.get("expired") is None
    assert await db.fetchone("SELECT key FROM kv WHERE key = ?", ("expired",)) is None

    await repository.delete("settings")
    assert await repository.get("settings") is None


async def test_entity_json_crud_and_table_injection_defense(db: Database) -> None:
    """JSON entities only use allowed static table statements."""
    repository = EntityJsonRepository(db)
    payload = {"id": "agent-1", "name": "Curator"}
    await repository.save("agents", "agent-1", payload)

    assert await repository.get("agents", "agent-1") == payload
    assert await repository.list_all("agents") == [payload]

    await repository.delete("agents", "agent-1")
    assert await repository.get("agents", "agent-1") is None

    with pytest.raises(ValueError, match="unsupported entity table"):
        await repository.list_all("agents; DROP TABLE kv; --")


async def test_source_data_batch_deduplication_filtering_and_fts(db: Database) -> None:
    """Source data de-duplicates IDs and supports structured and FTS retrieval."""
    repository = SourceDataRepository(db)
    first = _item("item-1", "Artificial intelligence")
    duplicate = _item("item-1", "Artificial intelligence duplicate")
    second = _item("item-2", "Database systems", source="github")

    assert await repository.save_batch([first, second], "rss-adapter") == 2
    assert await repository.save_batch([duplicate], "rss-adapter") == 0

    filtered = await repository.query({"source": "rss", "limit": 10, "offset": 0})
    searched = await repository.search_fts("intelligence", limit=10)
    ranged = await repository.get_by_date_range("2026-07-16", "2026-07-16")

    assert [item.id for item in filtered] == ["item-1"]
    assert [item.id for item in searched] == ["item-1"]
    assert "<mark>intelligence</mark>" in searched[0].description.lower()
    assert {item.id for item in ranged} == {"item-1", "item-2"}


async def test_task_log_crud_with_field_whitelist(db: Database) -> None:
    """Task logs persist, update approved fields, and reject unknown ones."""
    repository = TaskLogRepository(db)
    log_id = await repository.create(
        TaskLog(
            task_id="task-1",
            task_name="Ingest",
            start_time="2026-07-16T00:00:00Z",
            status="running",
        ),
    )

    await repository.update(log_id, status="success", duration_ms=42, result_count=2)
    updated = await repository.get(log_id)

    assert updated is not None
    assert updated.status == "success"
    assert updated.duration_ms == 42
    assert updated.result_count == 2

    with pytest.raises(ValueError, match="unsupported task log field"):
        await repository.update(log_id, task_id="replacement")


async def test_api_key_repository_lifecycle(db: Database) -> None:
    """API key metadata supports lookup, status changes, and last-use updates."""
    repository = ApiKeyRepository(db)
    await repository.create(
        key_id="key-1",
        name="Integration",
        key_hash="hashed-secret",
        prefix="msk_123",
        source_fingerprint="fingerprint",
        verification_token="verify-token",
        status="active",
    )

    by_prefix = await repository.get_by_prefix("msk_123")
    by_token = await repository.get_by_token("verify-token")
    assert by_prefix is not None
    assert by_token is not None
    assert by_prefix["id"] == "key-1"

    await repository.update_status("key-1", "revoked")
    await repository.update_last_used("key-1")
    records = await repository.list_all()

    assert records[0]["status"] == "revoked"
    assert records[0]["last_used_at"] is not None
