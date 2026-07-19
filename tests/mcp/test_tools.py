"""Pure handler coverage using lightweight fake service context objects."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from multiscribe_agent.config import SystemSettings
from multiscribe_agent.core.publish_history import PublishHistory
from multiscribe_agent.infra.db import init_db
from multiscribe_agent.mcp.tools.digest_tools import digest_history
from multiscribe_agent.mcp.tools.kb_tools import knowledge_search
from multiscribe_agent.mcp.tools.publisher_tools import list_publishers, list_sources
from multiscribe_agent.mcp.tools.rss_tools import fetch_rss


class FakeIngestion:
    """Count adapter calls without network activity."""

    async def run_single(self, adapter_id: str, config: dict[str, object]) -> int:
        """Return a deterministic inserted count."""
        assert adapter_id == "rss"
        assert config == {"rss_url": "https://example.test/feed"}
        return 2


class FakeSourceData:
    """Return serializable source entries expected by the handler."""

    async def query(self, _: dict[str, object]) -> list[FakeItem]:
        """Return one deterministic normalized item."""
        return [FakeItem()]


class FakeItem:
    """Minimal model-dump compatible source item."""

    def model_dump(self, *, mode: str) -> dict[str, object]:
        """Return a JSON-safe source payload."""
        assert mode == "json"
        return {"id": "item", "title": "RSS"}


@dataclass
class FakeCapabilities:
    """Expose the P16 capability contract."""

    degraded: bool = True

    def as_dict(self) -> dict[str, bool]:
        """Return a degraded FTS-only capability map."""
        return {"fts": True, "vector": False, "embedding": False}


class FakeKB:
    """Return an empty search result without touching the real KB."""

    capabilities = FakeCapabilities()

    async def search(self, query: str, *, top_k: int, category_id: str | None):
        """Validate the handler's forwarded search values."""
        assert query == "knowledge"
        assert top_k == 3
        assert category_id == "category"
        return []


class FakeContext:
    """Small attribute-only context accepted by MCP handlers."""

    def __init__(self) -> None:
        """Provide fake ingestion, data, and KB services."""
        self.ingestion = FakeIngestion()
        self.source_data = FakeSourceData()
        self.kb_service = FakeKB()


@pytest.mark.asyncio
async def test_rss_and_kb_handlers_return_documented_shapes() -> None:
    """RSS trigger and KB search normalize their outputs without external I/O."""
    context = FakeContext()
    rss = await fetch_rss(
        {"adapter_id": "rss", "config": {"rss_url": "https://example.test/feed"}}, context
    )
    kb = await knowledge_search(
        {"query": "knowledge", "top_k": 3, "category_id": "category"}, context
    )
    assert rss == {
        "adapter_id": "rss",
        "fetched_count": 2,
        "items": [{"id": "item", "title": "RSS"}],
    }
    assert kb["degraded"] is True
    assert kb["capabilities"]["fts"] is True


@pytest.mark.asyncio
async def test_digest_history_handler_serializes_records() -> None:
    """Digest history returns JSON-safe datetime and result-data fields."""
    db = await init_db(":memory:")
    try:
        history = PublishHistory()
        await history.add(db, "feishu_bot", "success", "Title", "content", {"ok": True})
        context = type("Context", (), {"db": db, "publish_history": history})()
        result = await digest_history({"limit": 1}, context)
        assert result["records"][0]["title"] == "Title"
        assert result["records"][0]["result_data"] == {"ok": True}
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_source_and_publisher_handlers_are_read_only() -> None:
    """Listing tools return the documented keys with no configuration mutation."""
    settings = SystemSettings(_env_file=None)
    assert list((await list_sources({}, settings)).keys()) == ["sources"]
    assert list((await list_publishers({}, settings)).keys()) == ["publishers"]
