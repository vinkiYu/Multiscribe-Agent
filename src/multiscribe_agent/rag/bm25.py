"""Chinese-aware BM25 retrieval over the P66-owned content index."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from multiscribe_agent.infra.db_protocol import DatabaseProtocol
from multiscribe_agent.infra.dialect import DialectRepositoryMixin, PgDialect
from multiscribe_agent.rag.models import RetrievalScope
from multiscribe_agent.rag.schema import scope_predicate, tokenize_rag_query

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Bm25Hit:
    """One chunk returned by the RAG-owned keyword index."""

    chunk_id: str
    score: float


class RagBm25Retriever(DialectRepositoryMixin):
    """Query the SQLite FTS5 or PostgreSQL tsvector RAG index."""

    _db: DatabaseProtocol

    def __init__(self, db: DatabaseProtocol) -> None:
        """Bind the database without creating an index implicitly."""
        self._db = db
        self.index_ready = True

    async def search(
        self,
        query: str,
        scope: RetrievalScope,
        *,
        candidate_k: int = 20,
    ) -> list[Bm25Hit]:
        """Return scope-filtered BM25 candidates, or an empty degraded result."""
        raw_terms = tokenize_rag_query(query).replace('"', " ").strip()
        if not raw_terms or candidate_k < 1:
            return []
        terms = raw_terms
        predicate, scope_parameters = scope_predicate(scope)
        try:
            if isinstance(self._dialect, PgDialect):
                statement = (
                    "SELECT rc.chunk_id, "  # noqa: S608
                    "ts_rank_cd(rc.content_tsv, plainto_tsquery('simple', ?)) AS rank "
                    "FROM rag_chunks rc "
                    "WHERE rc.content_tsv @@ plainto_tsquery('simple', ?) "
                    f"AND {predicate} ORDER BY rank DESC LIMIT ?"
                )
                parameters: list[Any] = [terms, terms, *scope_parameters, candidate_k]
            else:
                terms = " ".join(
                    f'"{token.replace(chr(34), chr(34) * 2)}"' for token in raw_terms.split()
                )
                statement = (
                    "SELECT rc.chunk_id, bm25(rag_chunks_fts) AS rank "  # noqa: S608
                    "FROM rag_chunks_fts "
                    "JOIN rag_chunks rc ON rc.chunk_id = rag_chunks_fts.chunk_id "
                    f"WHERE rag_chunks_fts MATCH ? AND {predicate} "
                    "ORDER BY rank ASC LIMIT ?"
                )
                parameters = [terms, *scope_parameters, candidate_k]
            rows = await self._fetchall(statement, parameters)
        except Exception as exc:  # Backend-specific missing-index errors vary by driver.
            self.index_ready = False
            log.warning("rag_bm25_unavailable", error=type(exc).__name__)
            return []
        self.index_ready = True
        return [Bm25Hit(chunk_id=str(row["chunk_id"]), score=float(row["rank"])) for row in rows]


__all__ = ["Bm25Hit", "RagBm25Retriever"]
