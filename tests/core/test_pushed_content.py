"""Tests for cross-day digest content identity persistence."""

from __future__ import annotations

import pytest_asyncio

from multiscribe_agent.core.pushed_content import PushedContentRepository
from multiscribe_agent.infra.db import Database
from tests.db import init_test_database


@pytest_asyncio.fixture
async def db() -> Database:
    """Provide a temporary initialized database for repository tests."""
    database = await init_test_database()
    try:
        yield database
    finally:
        await database.close()


async def test_pushed_content_schema_has_composite_primary_key_and_index(db: Database) -> None:
    """Initialization creates the table with the documented key and lookup index."""
    columns = await db.fetchall(
        "SELECT attribute.attname AS name, "
        "key.position AS position "
        "FROM pg_index AS index "
        "CROSS JOIN LATERAL unnest(index.indkey) WITH ORDINALITY "
        "AS key(attnum, position) "
        "JOIN pg_attribute AS attribute "
        "ON attribute.attrelid = index.indrelid "
        "AND attribute.attnum = key.attnum "
        "WHERE index.indrelid = 'public.pushed_content'::regclass "
        "AND index.indisprimary"
    )
    primary_key = {str(row["name"]): int(row["position"]) for row in columns}
    assert primary_key == {"content_hash": 1, "digest_date": 2}

    indexes = await db.fetchall(
        "SELECT indexname FROM pg_indexes "
        "WHERE schemaname = 'public' AND tablename = 'pushed_content'"
    )
    assert any(str(row["indexname"]) == "idx_pushed_content_pushed_at" for row in indexes)


async def test_add_is_idempotent_for_same_hash_and_digest_date(db: Database) -> None:
    """Repeated writes for one day do not create duplicate rows or raise errors."""
    repository = PushedContentRepository()
    for title in ("first title", "second title"):
        await repository.add(
            db,
            content_hash="hash-1",
            url="https://example.test/article/",
            digest_date="2026-07-17",
            title=title,
        )

    rows = await db.fetchall("SELECT * FROM pushed_content")
    assert len(rows) == 1
    assert rows[0]["url"] == "https://example.test/article"
    assert rows[0]["title"] == "first title"


async def test_recent_identities_use_inclusive_since_date_boundary(db: Database) -> None:
    """Today is included while records before the requested window are excluded."""
    repository = PushedContentRepository()
    await repository.add(
        db,
        content_hash="old",
        url="https://example.test/old",
        digest_date="2026-07-15",
        title="old",
    )
    await repository.add(
        db,
        content_hash="yesterday",
        url="https://example.test/yesterday/",
        digest_date="2026-07-16",
        title="yesterday",
    )
    await repository.add(
        db,
        content_hash="today",
        url="HTTPS://EXAMPLE.TEST/today/",
        digest_date="2026-07-17",
        title="today",
    )

    assert await repository.recent_hashes(db, since_date="2026-07-17") == {"today"}
    assert await repository.recent_urls(db, since_date="2026-07-17") == {
        "https://example.test/today"
    }
    assert await repository.recent_hashes(db, since_date="2026-07-16") == {"yesterday", "today"}
    assert await repository.recent_urls(db, since_date="2026-07-16") == {
        "https://example.test/yesterday",
        "https://example.test/today",
    }
