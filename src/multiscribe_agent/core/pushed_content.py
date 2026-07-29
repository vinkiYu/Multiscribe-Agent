"""Persistence boundary for content fingerprints already sent in a digest."""

from __future__ import annotations

from datetime import UTC, datetime

from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.dialect import ExplicitDatabaseDialectMixin, PgDialect


def _normalize_url(value: str) -> str:
    """Apply the digest URL identity convention to stored and returned URLs."""
    return value.strip().rstrip("/").casefold()


class PushedContentRepository(ExplicitDatabaseDialectMixin):
    """Store cross-day digest content identities independently of publish outcomes."""

    async def add(
        self,
        db: Database,
        *,
        content_hash: str,
        url: str,
        digest_date: str,
        title: str,
    ) -> None:
        """Record one pushed item, ignoring duplicate writes for the same digest date."""
        statement = (
            """
            INSERT INTO pushed_content(content_hash, url, digest_date, pushed_at, title)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            """
            if isinstance(self._dialect_for(db), PgDialect)
            else """
            INSERT OR IGNORE INTO pushed_content(
                content_hash, url, digest_date, pushed_at, title
            ) VALUES (?, ?, ?, ?, ?)
            """
        )
        await self._execute(
            db,
            statement,
            (
                content_hash,
                _normalize_url(url),
                digest_date,
                datetime.now(UTC).isoformat(),
                title,
            ),
        )

    async def recent_hashes(self, db: Database, *, since_date: str) -> set[str]:
        """Return hashes pushed on or after the inclusive date boundary."""
        rows = await self._fetchall(
            db,
            "SELECT content_hash FROM pushed_content WHERE digest_date >= ?",
            (since_date,),
        )
        return {str(row["content_hash"]) for row in rows}

    async def recent_urls(self, db: Database, *, since_date: str) -> set[str]:
        """Return normalized URLs pushed on or after the inclusive date boundary."""
        rows = await self._fetchall(
            db,
            "SELECT url FROM pushed_content WHERE digest_date >= ?",
            (since_date,),
        )
        return {_normalize_url(str(row["url"])) for row in rows}
