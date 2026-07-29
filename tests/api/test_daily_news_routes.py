"""Public daily-news filtering for preview approval states."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from multiscribe_agent.api.routes.daily_news import read_daily_news
from multiscribe_agent.core.daily_digest_archive import DailyDigestArchive
from multiscribe_agent.infra.db import init_db
from multiscribe_agent.renderers.feishu_card import DigestItem
from multiscribe_agent.renderers.models import CuratedDigest


def _digest(digest_date: str) -> CuratedDigest:
    """Build a compact digest snapshot for public route tests."""
    return CuratedDigest(
        date=digest_date,
        title=f"Digest {digest_date}",
        summary="Public summary",
        total_scanned=1,
        items=[
            DigestItem(
                title="Agent item",
                summary="Public item summary",
                url=f"https://example.test/{digest_date}",
                source="RSS",
                score=8.0,
            )
        ],
    )


@pytest.mark.asyncio
async def test_public_daily_news_excludes_pending_and_rejected_archives() -> None:
    """Public navigation and date lookup expose only approved publication states."""
    db = await init_db(":memory:")
    try:
        archive = DailyDigestArchive()
        await archive.upsert(db, _digest("2026-07-26"), approval_status="pending")
        await archive.upsert(db, _digest("2026-07-27"), approval_status="rejected")
        await archive.upsert(db, _digest("2026-07-28"), approval_status="published")
        await archive.upsert(db, _digest("2026-07-29"), approval_status="approved")
        context = SimpleNamespace(db=db)

        response = await read_daily_news(None, 10, context)  # type: ignore[arg-type]

        assert [item["date"] for item in response["archives"]] == [
            "2026-07-29",
            "2026-07-28",
        ]
        assert response["digest"]["date"] == "2026-07-29"  # type: ignore[index]
        with pytest.raises(HTTPException) as error:
            await read_daily_news(date(2026, 7, 26), 10, context)  # type: ignore[arg-type]
        assert error.value.status_code == 404
    finally:
        await db.close()
