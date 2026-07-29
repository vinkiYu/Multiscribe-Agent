from __future__ import annotations

import pytest

from multiscribe_agent.core.publish_history import PublishHistory
from multiscribe_agent.infra.db import init_db


@pytest.mark.asyncio
async def test_summary_groups_delivery_status_and_empty_is_zero() -> None:
    db = await init_db(":memory:")
    try:
        history = PublishHistory()
        assert await history.summary(db) == {"total": 0, "success": 0, "error": 0}
        await history.add(db, "feishu_bot", "success", "ok", "body", {})
        await history.add(db, "wecom_bot", "error", "bad", "body", {})
        assert await history.summary(db) == {"total": 2, "success": 1, "error": 1}
    finally:
        await db.close()
