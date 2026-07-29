"""Backend-specific full-text search SQL generation."""

from __future__ import annotations

from dataclasses import dataclass

from multiscribe_agent.infra.text_tokenize import tokenize_for_fts


@dataclass(frozen=True, slots=True)
class FtsQueryBuilder:
    """Generate equivalent FTS queries for SQLite FTS5 and PostgreSQL tsvector."""

    backend: str

    def __post_init__(self) -> None:
        """Reject unknown backend names before they can select the wrong SQL."""
        if self.backend not in {"sqlite", "postgres"}:
            raise ValueError(f"unsupported FTS backend: {self.backend!r}")

    def search_chunks_sql(self, query: str, limit: int) -> tuple[str, tuple[object, ...]]:
        """Build a chunk search query and its bound parameters."""
        bounded_limit = max(limit, 0)
        if self.backend == "postgres":
            terms = tokenize_for_fts(query)
            return (
                """
                SELECT kc.id, kc.document_id, kc.content,
                       ts_rank(kcf.content_tsv, plainto_tsquery('simple', $1)) AS rank
                FROM kb_chunks_fts kcf
                JOIN kb_chunks kc ON kc.id = kcf.chunk_id
                WHERE kcf.content_tsv @@ plainto_tsquery('simple', $2)
                ORDER BY rank DESC
                LIMIT $3
                """,
                (terms, terms, bounded_limit),
            )
        return (
            """
            SELECT kb_chunks.id, kb_chunks.document_id, kb_chunks.content
            FROM kb_chunks_fts
            JOIN kb_chunks ON kb_chunks.rowid = kb_chunks_fts.rowid
            WHERE kb_chunks_fts MATCH ?
            ORDER BY bm25(kb_chunks_fts)
            LIMIT ?
            """,
            (query, bounded_limit),
        )

    def search_source_data_sql(self, query: str, limit: int) -> tuple[str, tuple[object, ...]]:
        """Build source-content FTS SQL with a backend-appropriate highlight."""
        bounded_limit = max(limit, 0)
        if self.backend == "postgres":
            terms = tokenize_for_fts(query)
            return (
                """
                SELECT sd.*,
                       ts_headline(
                           'simple', sd.description, $1,
                           'StartSel=<mark>, StopSel=</mark>, MaxWords=50, MinWords=10'
                       ) AS highlight
                FROM source_data_fts sdf
                JOIN source_data sd ON sd.id = sdf.row_id
                WHERE sdf.description_tsv @@ plainto_tsquery('simple', $2)
                ORDER BY ts_rank(sdf.description_tsv, plainto_tsquery('simple', $3)) DESC
                LIMIT $4
                """,
                (terms, terms, terms, bounded_limit),
            )
        return (
            """
            SELECT source_data.*,
                snippet(source_data_fts, 1, '<mark>', '</mark>', '...', 12) AS highlight
            FROM source_data_fts
            JOIN source_data ON source_data_fts.rowid = source_data.rowid
            WHERE source_data_fts MATCH ?
            ORDER BY bm25(source_data_fts)
            LIMIT ?
            """,
            (query, bounded_limit),
        )

    def search_memories_sql(self, query: str, limit: int) -> tuple[str, tuple[object, ...]]:
        """Build memory FTS SQL with explicit primary-key joins on PostgreSQL."""
        bounded_limit = max(limit, 0)
        if self.backend == "postgres":
            terms = tokenize_for_fts(query)
            return (
                """
                SELECT am.id, am.content, am.tags, am.data
                FROM agent_memories_fts amf
                JOIN agent_memories am ON am.id = amf.row_id
                WHERE amf.content_tsv @@ plainto_tsquery('simple', $1)
                ORDER BY ts_rank(amf.content_tsv, plainto_tsquery('simple', $2)) DESC
                LIMIT $3
                """,
                (terms, terms, bounded_limit),
            )
        return (
            """
            SELECT agent_memories.id, agent_memories.content,
                   agent_memories.tags, agent_memories.data
            FROM agent_memories_fts
            JOIN agent_memories ON agent_memories.rowid = agent_memories_fts.rowid
            WHERE agent_memories_fts MATCH ?
            ORDER BY bm25(agent_memories_fts)
            LIMIT ?
            """,
            (query, bounded_limit),
        )
