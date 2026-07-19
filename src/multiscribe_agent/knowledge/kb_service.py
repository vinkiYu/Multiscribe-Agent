"""Knowledge-base persistence, ingestion, deduplication, and retrieval orchestration."""

from __future__ import annotations

import hashlib
import json
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from multiscribe_agent.domain.models import KBCategory, KBChunk, KBDocument
from multiscribe_agent.infra.db import Database
from multiscribe_agent.knowledge.document_processor import DocumentProcessor
from multiscribe_agent.knowledge.embedding_service import (
    EmbeddingService,
    EmbeddingUnavailableError,
)
from multiscribe_agent.knowledge.retriever import RetrievalHit, Retriever
from multiscribe_agent.knowledge.vector_store import VectorStore, VectorStoreUnavailable


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


class KBService:
    """Coordinate local document parsing, SQLite persistence, and hybrid retrieval."""

    def __init__(
        self,
        db: Database,
        processor: DocumentProcessor,
        embeddings: EmbeddingService | None,
        vector_store: VectorStore | None,
        retriever: Retriever | None,
    ) -> None:
        self._db = db
        self._processor = processor
        self._embeddings = embeddings
        self._vector_store = vector_store
        self._retriever = retriever or Retriever(db, vector_store, embeddings)

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
        await self._db.execute(
            "INSERT INTO kb_categories(id, data) VALUES (?, ?)",
            (category.id, _dump_model(category)),
        )
        return category

    async def ingest_file(
        self, *, file_path: Path, category_id: str, name: str, summary: str = ""
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
    ) -> KBDocument:
        """Chunk, deduplicate, optionally vectorize, and persist direct text content."""
        if not text.strip() or not name.strip():
            raise ValueError("document text and name must not be empty")
        await self._require_category(category_id)
        from multiscribe_agent.knowledge.chunking import split_text

        document_id = str(uuid4())
        now = _timestamp()
        candidates = split_text(text)
        chunks: list[KBChunk] = []
        for candidate in candidates:
            digest = hashlib.sha256(candidate.text.encode()).hexdigest()
            known = await self._db.fetchone(
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
        )
        await self._db.execute(
            "INSERT INTO kb_documents(id, category_id, data) VALUES (?, ?, ?)",
            (document.id, document.category_id, _dump_model(document)),
        )
        for chunk in chunks:
            await self._db.execute(
                "INSERT INTO kb_chunks(id, document_id, content, metadata) VALUES (?, ?, ?, ?)",
                (chunk.id, chunk.document_id, chunk.content, _dump_object(chunk.metadata)),
            )
            await self._db.execute(
                "INSERT INTO kb_chunk_dedup(content_hash, chunk_id, created_at) VALUES (?, ?, ?)",
                (str(chunk.metadata["sha256"]), chunk.id, datetime.now(UTC).isoformat()),
            )
        await self._store_vectors(chunks)
        return document

    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        category_id: str | None = None,
        deduplicate: bool = True,
        similarity_threshold: float = 0.95,
    ) -> list[RetrievalHit]:
        """Search candidates then apply category and duplicate filtering."""
        hits = await self._retriever.search(query, top_k=top_k * 3)
        if category_id is not None:
            hits = await self._filter_category(hits, category_id)
        if deduplicate:
            hits = await self._deduplicate_hits(hits, similarity_threshold)
        return hits[:top_k]

    async def list_categories(self) -> list[KBCategory]:
        """Return categories with live document counts."""
        rows = await self._db.fetchall("SELECT id, data FROM kb_categories ORDER BY id")
        categories: list[KBCategory] = []
        for row in rows:
            raw = json.loads(str(row["data"]))
            count = await self._db.fetchone(
                "SELECT COUNT(*) AS count FROM kb_documents WHERE category_id = ?", (row["id"],)
            )
            raw["document_count"] = int(count["count"]) if count is not None else 0
            categories.append(KBCategory.model_validate(raw))
        return categories

    async def list_documents(self, category_id: str | None = None) -> list[KBDocument]:
        """Return persisted document metadata, optionally restricted to a category."""
        if category_id is None:
            rows = await self._db.fetchall("SELECT data FROM kb_documents ORDER BY id DESC")
        else:
            rows = await self._db.fetchall(
                "SELECT data FROM kb_documents WHERE category_id = ? ORDER BY id DESC",
                (category_id,),
            )
        return [KBDocument.model_validate(json.loads(str(row["data"]))) for row in rows]

    async def delete_document(self, document_id: str) -> None:
        """Delete one document, its chunks, vectors, FTS rows, and exact-dedup records."""
        rows = await self._db.fetchall(
            "SELECT id FROM kb_chunks WHERE document_id = ?", (document_id,)
        )
        for row in rows:
            chunk_id = str(row["id"])
            if self._vector_store is not None:
                with suppress(VectorStoreUnavailable):
                    await self._vector_store.delete(chunk_id)
            await self._db.execute("DELETE FROM kb_chunk_dedup WHERE chunk_id = ?", (chunk_id,))
        await self._db.execute("DELETE FROM kb_chunks WHERE document_id = ?", (document_id,))
        await self._db.execute("DELETE FROM kb_documents WHERE id = ?", (document_id,))

    async def move_to_memory(self, document_id: str, target_memory_category: str) -> int:
        """Copy unique document chunks into P17-compatible memory records."""
        rows = await self._db.fetchall(
            "SELECT content FROM kb_chunks WHERE document_id = ? ORDER BY rowid", (document_id,)
        )
        inserted = 0
        for row in rows:
            content = str(row["content"])
            digest = hashlib.sha256(content.encode()).hexdigest()
            existing = await self._db.fetchone(
                "SELECT id FROM agent_memories WHERE json_extract(data, '$.sha256') = ?",
                (digest,),
            )
            if existing is not None:
                continue
            await self._db.execute(
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

    async def _require_category(self, category_id: str) -> None:
        """Reject ingestion that references no durable category."""
        row = await self._db.fetchone("SELECT id FROM kb_categories WHERE id = ?", (category_id,))
        if row is None:
            raise ValueError("knowledge-base category was not found")

    async def _filter_category(
        self, hits: list[RetrievalHit], category_id: str
    ) -> list[RetrievalHit]:
        """Keep only retrieval results owned by the requested category."""
        documents = await self._db.fetchall(
            "SELECT id FROM kb_documents WHERE category_id = ?", (category_id,)
        )
        document_ids = {str(row["id"]) for row in documents}
        return [hit for hit in hits if hit.document_id in document_ids]

    async def _deduplicate_hits(
        self, hits: list[RetrievalHit], threshold: float
    ) -> list[RetrievalHit]:
        """Remove exact repeats and highly similar adjacent chunks from one document."""
        seen_hashes: set[str] = set()
        kept: list[RetrievalHit] = []
        vectors: dict[str, list[float]] = {}
        if self._embeddings is not None:
            try:
                vectors = dict(
                    zip(
                        [hit.chunk_id for hit in hits],
                        await self._embeddings.encode([hit.content for hit in hits]),
                        strict=True,
                    )
                )
            except EmbeddingUnavailableError:
                vectors = {}
        for hit in hits:
            digest = hashlib.sha256(hit.content.encode()).hexdigest()
            if digest in seen_hashes:
                continue
            previous = next(
                (item for item in reversed(kept) if item.document_id == hit.document_id), None
            )
            if (
                previous is not None
                and hit.chunk_id in vectors
                and previous.chunk_id in vectors
                and EmbeddingService.cosine_similarity(
                    vectors[hit.chunk_id], vectors[previous.chunk_id]
                )
                > threshold
            ):
                continue
            seen_hashes.add(digest)
            kept.append(hit)
        return kept


def _timestamp() -> int:
    """Return current UTC seconds in the domain model's existing integer format."""
    return int(datetime.now(UTC).timestamp())


def _dump_model(model: KBCategory | KBDocument) -> str:
    """Serialize a frozen domain model for the existing JSON-backed table schema."""
    return model.model_dump_json()


def _dump_object(value: dict[str, object]) -> str:
    """Serialize structured metadata deterministically."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
