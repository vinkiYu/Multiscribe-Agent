"""Knowledge-base persistence, ingestion, deduplication, and RAG facade."""

from __future__ import annotations

import hashlib
import json
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import structlog

from multiscribe_agent.domain.models import KBCategory, KBChunk, KBDocument
from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.dialect import DialectRepositoryMixin, PgDialect
from multiscribe_agent.knowledge.document_processor import DocumentProcessor
from multiscribe_agent.knowledge.embedding_service import (
    EmbeddingService,
    EmbeddingUnavailableError,
)
from multiscribe_agent.knowledge.vector_store import VectorStore, VectorStoreUnavailable
from multiscribe_agent.rag.adapter import adapt_kb_document
from multiscribe_agent.rag.index_version import make_index_version
from multiscribe_agent.rag.indexing import RagIndexRegistry
from multiscribe_agent.rag.models import RetrievalScope, RetrievedEvidence
from multiscribe_agent.rag.ports import RagServiceProtocol
from multiscribe_agent.rag.schema import RagChunksStore

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class KBSearchHit:
    """Compatibility view of one RAG evidence item for KB-facing callers."""

    chunk_id: str
    document_id: str
    content: str
    score: float
    source: list[str]


@dataclass(frozen=True, slots=True)
class KBCapabilities:
    """The optional retrieval features available to this process."""

    vector_enabled: bool
    embedding_enabled: bool
    fts_enabled: bool = True

    @property
    def degraded(self) -> bool:
        """Return whether hybrid retrieval is currently reduced to FTS5."""
        return not (self.vector_enabled and self.embedding_enabled)

    def as_dict(self) -> dict[str, bool]:
        """Return API-safe capability names."""
        return {
            "vector": self.vector_enabled,
            "embedding": self.embedding_enabled,
            "fts": self.fts_enabled,
            "degraded": self.degraded,
        }


class KBService(DialectRepositoryMixin):
    """Coordinate local document parsing, persistence, and the RAG search facade."""

    def __init__(
        self,
        db: Database,
        processor: DocumentProcessor,
        embeddings: EmbeddingService | None,
        vector_store: VectorStore | None,
        rag_service: RagServiceProtocol | None = None,
        default_user_id: str = "admin",
    ) -> None:
        self._db = db
        self._processor = processor
        self._embeddings = embeddings
        self._vector_store = vector_store
        self._rag_service = rag_service
        self._default_user_id = default_user_id.strip() or "admin"

    @property
    def capabilities(self) -> KBCapabilities:
        """Expose whether optional vector and embedding features are active."""
        return KBCapabilities(self._vector_store is not None, self._embeddings is not None)

    async def create_category(self, name: str, description: str = "") -> KBCategory:
        """Create one durable category with an opaque identifier."""
        if not name.strip():
            raise ValueError("category name must not be empty")
        now = _timestamp()
        category = KBCategory(
            id=str(uuid4()),
            name=name.strip(),
            description=description,
            document_count=0,
            last_updated_at=now,
        )
        await self._execute(
            "INSERT INTO kb_categories(id, data) VALUES (?, ?)",
            (category.id, _dump_model(category)),
        )
        return category

    async def ingest_file(
        self,
        *,
        file_path: Path,
        category_id: str,
        name: str,
        summary: str = "",
        owner_user_id: str = "admin",
    ) -> KBDocument:
        """Parse one supported file then store its extracted text."""
        text, _ = await self._processor.process(file_path)
        return await self.ingest_text(
            text=text,
            category_id=category_id,
            name=name,
            summary=summary,
            file_name=file_path.name,
            kind=file_path.suffix,
            owner_user_id=owner_user_id,
        )

    async def ingest_text(
        self,
        *,
        text: str,
        category_id: str,
        name: str,
        summary: str = "",
        file_name: str = "",
        kind: str = "text",
        owner_user_id: str = "admin",
    ) -> KBDocument:
        """Chunk, deduplicate, optionally vectorize, and persist direct text content."""
        if not text.strip() or not name.strip() or not owner_user_id.strip():
            raise ValueError("document text and name must not be empty")
        await self._require_category(category_id)
        from multiscribe_agent.knowledge.chunking import split_text

        document_id = str(uuid4())
        now = _timestamp()
        candidates = split_text(text)
        chunks: list[KBChunk] = []
        for candidate in candidates:
            digest = hashlib.sha256(candidate.text.encode()).hexdigest()
            known = await self._fetchone(
                "SELECT chunk_id FROM kb_chunk_dedup WHERE content_hash = ?", (digest,)
            )
            if known is not None:
                continue
            chunk = KBChunk(
                id=str(uuid4()),
                document_id=document_id,
                content=candidate.text,
                index=candidate.index,
                metadata={
                    "char_start": candidate.char_start,
                    "char_end": candidate.char_end,
                    "sha256": digest,
                },
            )
            chunks.append(chunk)
        document = KBDocument(
            id=document_id,
            category_id=category_id,
            name=name.strip(),
            file_name=file_name or name.strip(),
            type=kind.lstrip(".") or "text",
            summary=summary,
            chunk_count=len(chunks),
            created_at=now,
            updated_at=now,
            owner_user_id=owner_user_id.strip(),
        )
        await self._execute(
            "INSERT INTO kb_documents(id, category_id, data) VALUES (?, ?, ?)",
            (document.id, document.category_id, _dump_model(document)),
        )
        for chunk in chunks:
            await self._execute(
                "INSERT INTO kb_chunks(id, document_id, content, metadata) VALUES (?, ?, ?, ?)",
                (chunk.id, chunk.document_id, chunk.content, _dump_object(chunk.metadata)),
            )
            await self._execute(
                "INSERT INTO kb_chunk_dedup(content_hash, chunk_id, created_at) VALUES (?, ?, ?)",
                (str(chunk.metadata["sha256"]), chunk.id, datetime.now(UTC).isoformat()),
            )
        await self._store_vectors(chunks)
        await self._sync_rag_index(document, chunks)
        return document

    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        category_id: str | None = None,
        deduplicate: bool = True,
        similarity_threshold: float = 0.95,
        user_id: str | None = None,
    ) -> list[KBSearchHit]:
        """Delegate KB retrieval to the P66 RAG service without legacy RRF code."""
        del deduplicate, similarity_threshold
        if self._rag_service is None or not query.strip() or top_k < 1:
            return []
        scope = RetrievalScope(
            user_id=(user_id or self._default_user_id).strip() or self._default_user_id,
            categories=[category_id] if category_id else [],
            doc_types=["kb"],
        )
        evidence = await self._rag_service.retrieve(query, scope, top_k=top_k)
        return [_as_search_hit(item) for item in evidence]

    async def list_categories(self) -> list[KBCategory]:
        """Return categories with live document counts."""
        rows = await self._fetchall("SELECT id, data FROM kb_categories ORDER BY id")
        categories: list[KBCategory] = []
        for row in rows:
            raw = json.loads(str(row["data"]))
            count = await self._fetchone(
                "SELECT COUNT(*) AS count FROM kb_documents WHERE category_id = ?", (row["id"],)
            )
            raw["document_count"] = int(count["count"]) if count is not None else 0
            categories.append(KBCategory.model_validate(raw))
        return categories

    async def list_documents(self, category_id: str | None = None) -> list[KBDocument]:
        """Return persisted document metadata, optionally restricted to a category."""
        if category_id is None:
            rows = await self._fetchall("SELECT data FROM kb_documents ORDER BY id DESC")
        else:
            rows = await self._fetchall(
                "SELECT data FROM kb_documents WHERE category_id = ? ORDER BY id DESC",
                (category_id,),
            )
        return [KBDocument.model_validate(json.loads(str(row["data"]))) for row in rows]

    async def delete_document(self, document_id: str) -> None:
        """Delete one document, its chunks, vectors, FTS rows, and exact-dedup records."""
        rows = await self._fetchall(
            "SELECT id FROM kb_chunks WHERE document_id = ?", (document_id,)
        )
        for row in rows:
            chunk_id = str(row["id"])
            if self._vector_store is not None:
                with suppress(VectorStoreUnavailable):
                    await self._vector_store.delete(chunk_id)
            await self._execute("DELETE FROM kb_chunk_dedup WHERE chunk_id = ?", (chunk_id,))
        await self._delete_rag_document(document_id, len(rows))
        await self._execute("DELETE FROM kb_chunks WHERE document_id = ?", (document_id,))
        await self._execute("DELETE FROM kb_documents WHERE id = ?", (document_id,))

    async def move_to_memory(self, document_id: str, target_memory_category: str) -> int:
        """Copy unique document chunks into P17-compatible memory records."""
        order_column = "id" if isinstance(self._dialect, PgDialect) else "rowid"
        rows = await self._fetchall(
            f"SELECT content FROM kb_chunks WHERE document_id = ? ORDER BY {order_column}",  # noqa: S608 - fixed dialect expression.
            (document_id,),
        )
        inserted = 0
        for row in rows:
            content = str(row["content"])
            digest = hashlib.sha256(content.encode()).hexdigest()
            existing = await self._fetchone(
                f"SELECT id FROM agent_memories WHERE {self._json_extract('data', 'sha256')} = ?",  # noqa: S608 - identifiers are fixed constants.
                (digest,),
            )
            if existing is not None:
                continue
            await self._execute(
                "INSERT INTO agent_memories(id, content, tags, data) VALUES (?, ?, ?, ?)",
                (
                    str(uuid4()),
                    content,
                    json.dumps([target_memory_category], ensure_ascii=False),
                    _dump_object(
                        {
                            "importance": 5,
                            "created_at": _timestamp(),
                            "agent_id": None,
                            "metadata": {"document_id": document_id},
                            "category_id": target_memory_category,
                            "sha256": digest,
                        }
                    ),
                ),
            )
            inserted += 1
        return inserted

    async def _store_vectors(self, chunks: list[KBChunk]) -> None:
        """Best-effort vector persistence; text ingestion remains usable when unavailable."""
        if not chunks or self._embeddings is None or self._vector_store is None:
            return
        try:
            vectors = await self._embeddings.encode([chunk.content for chunk in chunks])
            for chunk, vector in zip(chunks, vectors, strict=True):
                await self._vector_store.upsert(chunk.id, vector)
        except (EmbeddingUnavailableError, VectorStoreUnavailable):
            return

    async def _sync_rag_index(self, document: KBDocument, chunks: list[KBChunk]) -> None:
        """Write KB text into the live RAG BM25 index after successful persistence."""
        if self._rag_service is None or not chunks:
            return
        try:
            adapted = adapt_kb_document(document, chunks, user_id=document.owner_user_id)
            registry = RagIndexRegistry(self._db)
            rag_chunks = RagChunksStore(self._db)
            await registry.ensure_schema()
            await rag_chunks.ensure_schema()
            indexed_at = datetime.now(UTC).isoformat()
            index_version = make_index_version()
            for chunk in adapted.chunks:
                await rag_chunks.upsert(chunk, adapted.document, indexed_at=indexed_at)
                await registry.upsert(
                    chunk,
                    adapted.document,
                    indexed_at=indexed_at,
                    index_version=index_version,
                )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            log.warning("kb_rag_live_index_degraded", error_type=type(exc).__name__)

    async def _delete_rag_document(self, document_id: str, chunk_count: int) -> None:
        """Remove derived RAG rows for a deleted KB document."""
        if self._rag_service is None:
            return
        try:
            registry = RagIndexRegistry(self._db)
            rag_chunks = RagChunksStore(self._db)
            for index in range(chunk_count):
                chunk_id = f"kb:{document_id}:{index}"
                await registry.delete(chunk_id)
                await rag_chunks.delete(chunk_id)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            log.warning("kb_rag_live_delete_degraded", error_type=type(exc).__name__)

    async def _require_category(self, category_id: str) -> None:
        """Reject ingestion that references no durable category."""
        row = await self._fetchone("SELECT id FROM kb_categories WHERE id = ?", (category_id,))
        if row is None:
            raise ValueError("knowledge-base category was not found")


def _timestamp() -> int:
    """Return current UTC seconds in the domain model's existing integer format."""
    return int(datetime.now(UTC).timestamp())


def _dump_model(model: KBCategory | KBDocument) -> str:
    """Serialize a frozen domain model for the existing JSON-backed table schema."""
    return model.model_dump_json()


def _dump_object(value: dict[str, object]) -> str:
    """Serialize structured metadata deterministically."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _as_search_hit(evidence: RetrievedEvidence) -> KBSearchHit:
    """Convert structured RAG evidence to the stable KB compatibility shape."""
    document_id = evidence.document.document_id.removeprefix("kb:")
    return KBSearchHit(
        chunk_id=evidence.chunk.chunk_id,
        document_id=document_id,
        content=evidence.chunk.content,
        score=evidence.score,
        source=[evidence.retrieval_source],
    )
