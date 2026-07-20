"""Typed persistence and FTS retrieval for agent memories."""

from __future__ import annotations

import hashlib
import json
from builtins import list as builtin_list

from multiscribe_agent.domain.models import MemoryEntry
from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.text_tokenize import tokenize_for_fts


class DuplicateEntryError(ValueError):
    """Reserved for callers that need to distinguish duplicate memory input."""


class MemoryEntryRepository:
    """Store validated memories using the existing table and FTS triggers."""

    def __init__(self, db: Database) -> None:
        """Bind this repository to an initialized SQLite database."""
        self._db = db

    async def save(self, entry: MemoryEntry) -> str:
        """Save one entry once by URL-plus-content hash and return its canonical id."""
        digest = self._digest(entry)
        existing = await self._db.fetchone(
            "SELECT id FROM agent_memories WHERE json_extract(data, '$.sha256') = ?", (digest,)
        )
        if existing is not None:
            return str(existing["id"])
        data = entry.model_dump(mode="json", exclude={"id", "content", "tags"})
        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("memory metadata must be an object")
        data["metadata"] = metadata
        data["sha256"] = digest
        data["category_id"] = self._category_id(entry)
        await self._db.execute(
            "INSERT INTO agent_memories(id, content, tags, data) VALUES (?, ?, ?, ?)",
            (
                entry.id,
                entry.content,
                json.dumps(entry.tags, ensure_ascii=False),
                json.dumps(data, ensure_ascii=False, sort_keys=True),
            ),
        )
        await self._db.execute(
            """
            UPDATE agent_memories_fts
            SET content = ?, tags = ?
            WHERE rowid = (SELECT rowid FROM agent_memories WHERE id = ?)
            """,
            (tokenize_for_fts(entry.content), tokenize_for_fts(json.dumps(entry.tags)), entry.id),
        )
        return entry.id

    async def save_batch(self, entries: list[MemoryEntry]) -> int:
        """Save unique entries and return how many new records were inserted."""
        inserted = 0
        for entry in entries:
            before = await self._db.fetchone(
                "SELECT id FROM agent_memories WHERE json_extract(data, '$.sha256') = ?",
                (self._digest(entry),),
            )
            await self.save(entry)
            if before is None:
                inserted += 1
        return inserted

    async def get(self, entry_id: str) -> MemoryEntry | None:
        """Return a memory by identifier, if present."""
        row = await self._db.fetchone(
            "SELECT id, content, tags, data FROM agent_memories WHERE id = ?", (entry_id,)
        )
        return self._entry_from_row(row) if row is not None else None

    async def list(
        self, category_id: str | None = None, tag: str | None = None, limit: int = 50
    ) -> builtin_list[MemoryEntry]:
        """List newest memory records filtered by optional category and tag."""
        statement, parameters = _list_statement(category_id, tag, limit)
        rows = await self._db.fetchall(statement, parameters)
        return [self._entry_from_row(row) for row in rows]

    async def delete(self, entry_id: str) -> bool:
        """Delete one memory record and let the existing trigger update FTS."""
        return await self._db.execute("DELETE FROM agent_memories WHERE id = ?", (entry_id,)) > 0

    async def fts_search(self, query: str, limit: int = 20) -> builtin_list[MemoryEntry]:
        """Find memories through the existing FTS5 table."""
        terms = tokenize_for_fts(query.replace("'", " "))
        if not terms:
            return []
        rows = await self._db.fetchall(
            """
            SELECT agent_memories.id, agent_memories.content,
                   agent_memories.tags, agent_memories.data
            FROM agent_memories_fts
            JOIN agent_memories ON agent_memories.rowid = agent_memories_fts.rowid
            WHERE agent_memories_fts MATCH ?
            ORDER BY bm25(agent_memories_fts)
            LIMIT ?
            """,
            (terms, max(1, min(limit, 50))),
        )
        return [self._entry_from_row(row) for row in rows]

    @staticmethod
    def _digest(entry: MemoryEntry) -> str:
        metadata_url = entry.metadata.get("url")
        url = metadata_url.strip() if isinstance(metadata_url, str) else ""
        return hashlib.sha256(f"{url}{entry.content}".encode()).hexdigest()

    @staticmethod
    def _category_id(entry: MemoryEntry) -> str | None:
        category = entry.metadata.get("category_id")
        return category if isinstance(category, str) and category.strip() else None

    @staticmethod
    def _entry_from_row(row: object) -> MemoryEntry:
        value = row
        data = json.loads(str(value["data"]))  # type: ignore[index]
        if not isinstance(data, dict):
            raise ValueError("memory data must be an object")
        tags = json.loads(str(value["tags"]))  # type: ignore[index]
        if not isinstance(tags, builtin_list) or not all(isinstance(tag, str) for tag in tags):
            raise ValueError("memory tags must be a string list")
        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("memory metadata must be an object")
        return MemoryEntry(
            id=str(value["id"]),  # type: ignore[index]
            content=str(value["content"]),  # type: ignore[index]
            importance=int(data.get("importance", 0)),
            tags=tags,
            created_at=int(data.get("created_at", 0)),
            agent_id=data.get("agent_id") if isinstance(data.get("agent_id"), str) else None,
            metadata={str(key): item for key, item in metadata.items()},
        )


def _list_statement(
    category_id: str | None, tag: str | None, limit: int
) -> tuple[str, builtin_list[object]]:
    """Select a static parameterized listing statement for optional filters."""
    bounded_limit = max(1, min(limit, 200))
    if category_id is not None and tag is not None:
        return (
            """
            SELECT id, content, tags, data FROM agent_memories
            WHERE json_extract(data, '$.category_id') = ? AND tags LIKE ?
            ORDER BY rowid DESC LIMIT ?
            """,
            [category_id, f'%"{tag}"%', bounded_limit],
        )
    if category_id is not None:
        return (
            """
            SELECT id, content, tags, data FROM agent_memories
            WHERE json_extract(data, '$.category_id') = ?
            ORDER BY rowid DESC LIMIT ?
            """,
            [category_id, bounded_limit],
        )
    if tag is not None:
        return (
            """
            SELECT id, content, tags, data FROM agent_memories
            WHERE tags LIKE ? ORDER BY rowid DESC LIMIT ?
            """,
            [f'%"{tag}"%', bounded_limit],
        )
    return (
        "SELECT id, content, tags, data FROM agent_memories ORDER BY rowid DESC LIMIT ?",
        [bounded_limit],
    )
