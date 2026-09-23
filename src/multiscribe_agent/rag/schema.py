"""Derived storage for the P66 hybrid retrieval index.

The RAG index is rebuildable state.  It intentionally lives beside the P66.2
manifest instead of changing the legacy ``source_data_fts`` or
``kb_chunks_fts`` paths.  SQLite stores a jieba-tokenized FTS5 shadow table;
PostgreSQL stores the same token stream in a ``tsvector`` column.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from multiscribe_agent.infra.db_protocol import DatabaseProtocol
from multiscribe_agent.infra.dialect import DialectRepositoryMixin, PgDialect, UpsertStyle
from multiscribe_agent.infra.text_tokenize import tokenize_for_fts
from multiscribe_agent.rag.models import KnowledgeChunk, KnowledgeDocument, RetrievalScope

_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")


def tokenize_rag_text(text: str) -> str:
    """Tokenize both sides of the RAG FTS path, with a deterministic CJK fallback.

    ``jieba`` remains the primary tokenizer.  When it is not installed (the
    supported optional-dependency mode), adding CJK unigrams and bigrams keeps
    a phrase query searchable instead of indexing one whole Chinese sentence
    as a single unicode61 token.
    """
    base = tokenize_for_fts(text)
    tokens: list[str] = [token for token in base.split() if token]
    for match in _CJK_RUN.finditer(text):
        value = match.group(0)
        tokens.extend(value[index : index + 2] for index in range(len(value) - 1))
        tokens.extend(value)
    return " ".join(dict.fromkeys(tokens))


def tokenize_rag_query(text: str) -> str:
    """Build an FTS query that avoids requiring an unsplittable CJK sentence token."""
    tokens = tokenize_rag_text(text).split()
    return " ".join(
        token
        for token in tokens
        if not (len(token) > 2 and all("\u3400" <= char <= "\u9fff" for char in token))
    )


def scope_predicate(scope: RetrievalScope, *, alias: str = "rc") -> tuple[str, list[object]]:
    """Render the common hard/soft scope predicates for a derived row alias."""
    clauses = [f"{alias}.user_id = ?"]
    parameters: list[object] = [scope.user_id]
    if scope.agent_id is not None:
        clauses.append(f"{alias}.agent_id = ?")
        parameters.append(scope.agent_id)
    _append_in_filter(clauses, parameters, f"{alias}.category", scope.categories)
    _append_in_filter(clauses, parameters, f"{alias}.source", scope.sources)
    _append_in_filter(clauses, parameters, f"{alias}.doc_type", scope.doc_types)
    if scope.time_from is not None:
        clauses.append(f"({alias}.published_at IS NULL OR {alias}.published_at >= ?)")
        parameters.append(scope.time_from)
    if scope.time_to is not None:
        clauses.append(f"({alias}.published_at IS NULL OR {alias}.published_at <= ?)")
        parameters.append(scope.time_to)
    return " AND ".join(clauses), parameters


def _append_in_filter(
    clauses: list[str], parameters: list[object], column: str, values: Sequence[str]
) -> None:
    """Append a parameterized ``IN`` predicate when a scope filter is present."""
    if not values:
        return
    placeholders = ", ".join("?" for _ in values)
    clauses.append(f"{column} IN ({placeholders})")
    parameters.extend(values)


class RagChunksStore(DialectRepositoryMixin):
    """Persist and query the rebuildable ``rag_chunks`` derived index."""

    _db: DatabaseProtocol

    def __init__(self, db: DatabaseProtocol) -> None:
        """Bind the backend-neutral database protocol."""
        self._db = db

    async def ensure_schema(self) -> None:
        """Create the RAG content table and its dialect-specific search index."""
        content_tsv = (
            "content_tsv tsvector"
            if isinstance(self._dialect, PgDialect)
            else "content_tsv TEXT NOT NULL"
        )
        await self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS rag_chunks (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                {content_tsv},
                published_at TEXT,
                category TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                agent_id TEXT
            )
            """
        )
        await self._execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_chunks_document ON rag_chunks(document_id)"
        )
        await self._execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_chunks_scope "
            "ON rag_chunks(user_id, doc_type, published_at)"
        )
        if not isinstance(self._dialect, PgDialect):
            await self._execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    content
                )
                """
            )

    async def exists(self, chunk_id: str) -> bool:
        """Return whether the derived content row exists."""
        row = await self._fetchone(
            "SELECT chunk_id FROM rag_chunks WHERE chunk_id = ?", (chunk_id,)
        )
        return row is not None

    async def upsert(
        self,
        chunk: KnowledgeChunk,
        document: KnowledgeDocument,
        *,
        indexed_at: str,
    ) -> None:
        """Upsert one chunk and keep SQLite's FTS shadow row in sync."""
        metadata = chunk.metadata
        agent_id = metadata.get("agent_id")
        agent_value = agent_id if isinstance(agent_id, str) and agent_id.strip() else None
        columns = (
            "chunk_id",
            "document_id",
            "doc_type",
            "user_id",
            "content",
            "content_tsv",
            "published_at",
            "category",
            "source",
            "title",
            "url",
            "agent_id",
        )
        if isinstance(self._dialect, PgDialect):
            statement = (
                "INSERT INTO rag_chunks ("  # noqa: S608
                + ", ".join(columns)
                + ") VALUES (?, ?, ?, ?, ?, to_tsvector('simple', ?), ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (chunk_id) DO UPDATE SET "
                "document_id = EXCLUDED.document_id, doc_type = EXCLUDED.doc_type, "
                "user_id = EXCLUDED.user_id, content = EXCLUDED.content, "
                "content_tsv = EXCLUDED.content_tsv, published_at = EXCLUDED.published_at, "
                "category = EXCLUDED.category, source = EXCLUDED.source, "
                "title = EXCLUDED.title, url = EXCLUDED.url, agent_id = EXCLUDED.agent_id"
            )
            parameters: list[Any] = [
                chunk.chunk_id,
                document.document_id,
                document.doc_type,
                document.user_id,
                chunk.content,
                tokenize_rag_text(chunk.content),
                document.published_at,
                document.category,
                document.source,
                document.title,
                document.url,
                agent_value,
            ]
            await self._execute(statement, parameters)
            return

        statement = self._upsert_sql(
            table="rag_chunks",
            columns=columns,
            style=UpsertStyle.ON_CONFLICT_DO_UPDATE,
            conflict_target=("chunk_id",),
            update_columns=tuple(column for column in columns if column != "chunk_id"),
        )
        await self._execute(
            statement,
            [
                chunk.chunk_id,
                document.document_id,
                document.doc_type,
                document.user_id,
                chunk.content,
                tokenize_rag_text(chunk.content),
                document.published_at,
                document.category,
                document.source,
                document.title,
                document.url,
                agent_value,
            ],
        )
        await self._execute("DELETE FROM rag_chunks_fts WHERE chunk_id = ?", (chunk.chunk_id,))
        await self._execute(
            "INSERT INTO rag_chunks_fts(chunk_id, content) VALUES (?, ?)",
            (chunk.chunk_id, tokenize_rag_text(chunk.content)),
        )

    async def delete(self, chunk_id: str) -> None:
        """Delete one chunk from both the content table and its FTS shadow."""
        if not isinstance(self._dialect, PgDialect):
            await self._execute("DELETE FROM rag_chunks_fts WHERE chunk_id = ?", (chunk_id,))
        await self._execute("DELETE FROM rag_chunks WHERE chunk_id = ?", (chunk_id,))

    async def get(self, chunk_id: str) -> Mapping[str, Any] | None:
        """Return one canonical derived row."""
        return await self._fetchone("SELECT * FROM rag_chunks WHERE chunk_id = ?", (chunk_id,))


__all__ = ["RagChunksStore", "scope_predicate", "tokenize_rag_query", "tokenize_rag_text"]
