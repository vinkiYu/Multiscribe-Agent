"""Unit and integration coverage for persistent publish history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from multiscribe_agent.agents.pipelines.daily_digest import (
    DailyDigestConfig,
    _DailyDigestStepExecutor,
)
from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings
from multiscribe_agent.core.publish_history import PublishHistory
from multiscribe_agent.infra.db import init_db


class FakePublishingService:
    """Return configured target outcomes without invoking an external publisher."""

    async def fanout(self, digest: object, targets: list[str]) -> dict[str, dict[str, object]]:
        """Return one success and one isolated failure for history persistence tests."""
        del digest
        return {
            target: (
                {"status": "success", "response": {"message_id": "ok"}}
                if target == "feishu_bot"
                else {"status": "error", "error": "delivery failed"}
            )
            for target in targets
        }


@pytest.mark.asyncio
async def test_add_and_query_round_trip_redacts_preview() -> None:
    """Stored records preserve result JSON while excluding credentials from previews."""
    db = await init_db(":memory:")
    try:
        history = PublishHistory()
        record_id = await history.add(
            db,
            publisher_id="feishu_bot",
            status="success",
            title="Daily digest",
            content="Bearer top-secret-token content",
            result_data={"message_id": "m-1"},
            adapter_name="rss",
        )

        records = await history.query(db, publisher_id="feishu_bot")

        assert records[0].id == record_id
        assert records[0].content_preview == "[REDACTED] content"
        assert records[0].result_data == {"message_id": "m-1"}
        assert records[0].adapter_name == "rss"
    finally:
        await db.close()


def test_sanitize_redacts_webhooks_keys_and_truncates_content() -> None:
    """Known delivery credentials never survive a stored content preview."""
    content = (
        "https://open.feishu.cn/open-apis/bot/v2/hook/secret-value "
        "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=secret-value "
        "https://oapi.dingtalk.com/robot/send?access_token=secret-value "
        "sk-abcdefghijklmnopqrstuvwxyz0123456789 " + "x" * 300
    )

    preview = PublishHistory.sanitize(content)

    assert preview.count("[REDACTED]") == 4
    assert "secret-value" not in preview
    assert len(preview) == 200


@pytest.mark.asyncio
async def test_query_filters_by_publisher_date_range_and_limit() -> None:
    """Query bounds and publisher filters operate on persisted rows."""
    db = await init_db(":memory:")
    try:
        history = PublishHistory()
        older_id = await history.add(db, "wecom_bot", "success", "Older", "content", {"ok": True})
        newest_id = await history.add(db, "feishu_bot", "error", "Newest", "content", {"ok": False})
        now = datetime.now(UTC)
        await db.execute(
            "UPDATE publish_history SET published_at = ? WHERE id = ?",
            ((now - timedelta(days=3)).isoformat(), older_id),
        )

        recent = await history.query(db, from_date=now - timedelta(days=1), limit=10)
        feishu = await history.query(db, publisher_id="feishu_bot", limit=1)

        assert [record.id for record in recent] == [newest_id]
        assert [record.id for record in feishu] == [newest_id]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_query_clamps_out_of_range_limits() -> None:
    """History queries keep direct callers within the documented safe limit."""
    db = await init_db(":memory:")
    try:
        history = PublishHistory()
        await history.add(db, "feishu_bot", "success", "Only", "content", {})

        assert len(await history.query(db, limit=0)) == 1
        assert len(await history.query(db, limit=999)) == 1
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_database_initialization_creates_publish_history_table() -> None:
    """The migration is part of normal database initialization and is idempotent."""
    db = await init_db(":memory:")
    try:
        row = await db.fetchone(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'publish_history'"
        )

        assert row is not None
        await db.migrate_publish_history()
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_pipeline_fanout_persists_each_target_outcome() -> None:
    """Pipeline fan-out writes independent success and error delivery rows."""
    db = await init_db(":memory:")
    try:
        history = PublishHistory()
        config = DailyDigestConfig(
            curate_agent_id="curator",
            targets=["feishu_bot", "wecom_bot"],
        )
        executor = _DailyDigestStepExecutor(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            FakePublishingService(),  # type: ignore[arg-type]
            config,
            "2026-07-19",
            db,
            history,
        )
        serialized_inputs = (
            '{\'curated\': \'[{"title": "News", "summary": "Summary", '
            '"url": "https://example.test", "source": "rss", "score": 1}]\', '
            "'overview': 'Digest overview'}"
        )

        await executor._fanout(serialized_inputs)
        records = await history.query(db, limit=10)

        assert {record.publisher_id for record in records} == {"feishu_bot", "wecom_bot"}
        assert {record.status for record in records} == {"success", "error"}
        error_record = next(record for record in records if record.status == "error")
        assert error_record.error_message == "delivery failed"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_api_returns_authenticated_history_records(tmp_path) -> None:
    """Registered API route returns the context-injected service's stored rows."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "history.sqlite"))
    context = ServiceContext(settings)
    await context.init()
    try:
        assert context.db is not None
        assert context.publish_history is not None
        await context.publish_history.add(
            context.db,
            "feishu_bot",
            "success",
            "API record",
            "content",
            {"ok": True},
        )
        app = create_app(settings, context)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            login = await client.post("/api/login", json={"password": "admin123"})
            token = login.json()["access_token"]
            response = await client.get(
                "/api/publish-history",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        assert response.json()[0]["title"] == "API record"
    finally:
        await context.close()


@pytest.mark.asyncio
async def test_api_rejects_unauthenticated_history_requests(tmp_path) -> None:
    """History records remain behind the project's existing JWT requirement."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "history.sqlite"))
    context = ServiceContext(settings)
    await context.init()
    try:
        app = create_app(settings, context)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/publish-history")

        assert response.status_code == 401
    finally:
        await context.close()
