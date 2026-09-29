"""PostgreSQL ``tsvector`` query builders used by repository search paths."""

from __future__ import annotations

from dataclasses import dataclass

from multiscribe_agent.infra.text_tokenize import tokenize_for_fts


@dataclass(frozen=True, slots=True)
class FtsQueryBuilder:
    """Build parameterised PostgreSQL full-text search statements."""

    def search_chunks_sql(self, query: str, limit: int) -> tuple[str, tuple[object, ...]]:
        """Build a ranked RAG chunk query."""
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
            (terms, terms, max(limit, 0)),
        )

    def search_source_data_sql(self, query: str, limit: int) -> tuple[str, tuple[object, ...]]:
        """Build a source-data query with PostgreSQL headline highlighting."""
        terms = tokenize_for_fts(query)
        return (
            """
            SELECT sd.*,
                   ts_headline(
                       'simple', sd.description, plainto_tsquery('simple', $1),
                       'StartSel=<mark>, StopSel=</mark>, MaxWords=50, MinWords=10'
                   ) AS highlight
            FROM source_data_fts sdf
            JOIN source_data sd ON sd.id = sdf.row_id
            WHERE sdf.description_tsv @@ plainto_tsquery('simple', $2)
            ORDER BY ts_rank(sdf.description_tsv, plainto_tsquery('simple', $3)) DESC
            LIMIT $4
            """,
            (terms, terms, terms, max(limit, 0)),
        )

    def search_memories_sql(self, query: str, limit: int) -> tuple[str, tuple[object, ...]]:
        """Build a ranked long-term-memory query."""
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
            (terms, terms, max(limit, 0)),
        )
