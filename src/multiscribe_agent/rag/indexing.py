"""Haystack indexing bridge backed by the existing :class:`VectorStorePort`.

Haystack is used as an in-memory pipeline DTO/orchestration layer only.  The
business database and vector store remain the system of record; no Haystack
``DocumentStore`` is created or written here.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect
from collections import defaultdict
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from types import ModuleType
from typing import Protocol, cast

import structlog

from multiscribe_agent.domain.ports import VectorStorePort
from multiscribe_agent.infra.db_protocol import DatabaseProtocol
from multiscribe_agent.infra.dialect import DialectRepositoryMixin, UpsertStyle
from multiscribe_agent.rag.adapter import AdaptedDocument
from multiscribe_agent.rag.models import KnowledgeChunk, KnowledgeDocument


@dataclass(frozen=True, slots=True)
class _FallbackDocument:
    """Minimal in-memory stand-in for Haystack's Document."""

    content: str
    meta: dict[str, object] | None = None


class _ComponentAPI:
    """Typed facade over Haystack's optional component decorator."""

    def __init__(self, implementation: object | None) -> None:
        """Keep the real decorator when Haystack is installed."""
        self._implementation = implementation

    def __call__(self, cls: type[object]) -> type[object]:
        """Decorate a component class or return it unchanged in fallback mode."""
        if self._implementation is None:
            return cls
        decorator = cast(Callable[[type[object]], type[object]], self._implementation)
        return decorator(cls)

    def output_types(
        self, **types: object
    ) -> Callable[[Callable[..., object]], Callable[..., object]]:
        """Decorate a component method with Haystack output metadata."""
        if self._implementation is None:
            return lambda function: function
        output_types = cast(
            Callable[..., Callable[[Callable[..., object]], Callable[..., object]]],
            self._implementation.output_types,  # type: ignore[attr-defined]
        )
        return output_types(**types)


class _FallbackPipeline:
    """Small pipeline fallback with the same call shape as Haystack 2.x."""

    def __init__(self) -> None:
        self._components: dict[str, object] = {}
        self._connections: list[tuple[str, str]] = []

    def add_component(self, name: str, instance: object) -> None:
        """Register one component."""
        self._components[name] = instance

    def connect(self, sender: str, receiver: str) -> None:
        """Connect one component output to the next input."""
        self._connections.append((sender, receiver))

    def run(self, data: dict[str, dict[str, object]]) -> dict[str, object]:
        """Execute the three local components in dependency order."""
        source = cast(_SourceComponent, self._components["source"])
        embedder = cast(_EmbeddingComponent, self._components["embedder"])
        sink = cast(_VectorSinkComponent, self._components["sink"])
        source_output = cast(dict[str, object], source.run(**data["source"]))
        embedding_output = cast(
            dict[str, object],
            embedder.run(chunks=cast(list[KnowledgeChunk], source_output["chunks"])),
        )
        sink_output = sink.run(
            embedded=cast(list[EmbeddedChunk], embedding_output["embedded"]),
            failed_document_ids=cast(list[str], embedding_output.get("failed_document_ids", [])),
            index_version=str(data["sink"]["index_version"]),
        )
        return {"sink": sink_output}


_haystack_module: ModuleType | None
try:  # pragma: no cover - optional dependency branch.
    _haystack_module = importlib.import_module("haystack")
except ImportError:  # pragma: no cover - local fallback keeps hermetic tests runnable.
    _haystack_module = None

_haystack_component = (
    _haystack_module.__dict__.get("component") if _haystack_module is not None else None
)
_haystack_pipeline = (
    _haystack_module.__dict__.get("Pipeline") if _haystack_module is not None else None
)
_haystack_document = (
    _haystack_module.__dict__.get("Document") if _haystack_module is not None else None
)
component = _ComponentAPI(_haystack_component)


class _PipelineLike(Protocol):
    """Minimal Haystack pipeline surface used by the async wrapper."""

    def add_component(self, name: str, instance: object) -> None:
        """Register one component."""

    def connect(self, sender: str, receiver: str) -> None:
        """Connect one component output to the next input."""

    def run(self, data: dict[str, dict[str, object]]) -> dict[str, object]:
        """Execute the synchronous pipeline."""


def _make_document(content: str, meta: dict[str, object]) -> object:
    """Create a real Haystack Document or a local DTO when Haystack is absent."""
    if _haystack_document is None:
        return _FallbackDocument(content=content, meta=meta)
    factory = cast(Callable[..., object], _haystack_document)
    return factory(content=content, meta=meta)


def _new_pipeline() -> _PipelineLike:
    """Create a real Haystack Pipeline or the deterministic local fallback."""
    if _haystack_pipeline is None:
        return _FallbackPipeline()
    factory = cast(Callable[[], _PipelineLike], _haystack_pipeline)
    return factory()


log = structlog.get_logger(__name__)


class BatchEmbedder(Protocol):
    """Async batch embedding surface used by the custom Haystack component."""

    async def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts in input order."""
        ...


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    """Chunk plus its embedding before vector-store persistence."""

    chunk: KnowledgeChunk
    embedding: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class IndexReport:
    """Summary of one incremental or full indexing pass."""

    indexed_chunk_ids: tuple[str, ...] = ()
    skipped_chunk_ids: tuple[str, ...] = ()
    deleted_chunk_ids: tuple[str, ...] = ()
    failed_document_ids: tuple[str, ...] = ()


class RagIndexRegistry(DialectRepositoryMixin):
    """Persist the document-to-vector index manifest in either SQL dialect."""

    _db: DatabaseProtocol

    def __init__(self, db: DatabaseProtocol) -> None:
        """Create a registry over an initialized backend-neutral database."""
        self._db = db

    async def ensure_schema(self) -> None:
        """Create the idempotent registry table and lookup indexes."""
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS rag_index_registry (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                user_id TEXT NOT NULL,
                indexed_at TEXT NOT NULL,
                index_version TEXT NOT NULL
            )
            """
        )
        await self._execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_index_registry_document "
            "ON rag_index_registry(document_id)"
        )
        await self._execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_index_registry_type ON rag_index_registry(doc_type)"
        )

    async def get_by_document(self, document_id: str) -> list[dict[str, object]]:
        """Return registry rows for one canonical document."""
        rows = await self._fetchall(
            "SELECT * FROM rag_index_registry WHERE document_id = ? ORDER BY chunk_id",
            (document_id,),
        )
        return [dict(row) for row in rows]

    async def get_by_chunk(self, chunk_id: str) -> dict[str, object] | None:
        """Return one registry row by its stable chunk ID."""
        row = await self._fetchone(
            "SELECT * FROM rag_index_registry WHERE chunk_id = ?", (chunk_id,)
        )
        return dict(row) if row is not None else None

    async def list_source_documents(self) -> list[dict[str, object]]:
        """Return all source-data rows for time-window pruning."""
        rows = await self._fetchall(
            "SELECT * FROM rag_index_registry WHERE doc_type = ?", ("source_data",)
        )
        return [dict(row) for row in rows]

    async def upsert(
        self,
        chunk: KnowledgeChunk,
        document: KnowledgeDocument,
        *,
        indexed_at: str,
        index_version: str,
    ) -> None:
        """Register one successfully persisted vector."""
        statement = self._upsert_sql(
            table="rag_index_registry",
            columns=(
                "chunk_id",
                "document_id",
                "doc_type",
                "content_hash",
                "user_id",
                "indexed_at",
                "index_version",
            ),
            style=UpsertStyle.ON_CONFLICT_DO_UPDATE,
            conflict_target=("chunk_id",),
            update_columns=(
                "document_id",
                "doc_type",
                "content_hash",
                "user_id",
                "indexed_at",
                "index_version",
            ),
        )
        await self._execute(
            statement,
            [
                chunk.chunk_id,
                document.document_id,
                document.doc_type,
                _content_hash(chunk.content),
                document.user_id,
                indexed_at,
                index_version,
            ],
        )

    async def delete(self, chunk_id: str) -> None:
        """Remove one registry row."""
        await self._execute("DELETE FROM rag_index_registry WHERE chunk_id = ?", (chunk_id,))


@component
class _SourceComponent:
    """Convert canonical models into in-memory Haystack Documents."""

    @component.output_types(
        documents=list[KnowledgeDocument],
        chunks=list[KnowledgeChunk],
    )
    def run(
        self,
        documents: list[KnowledgeDocument],
        chunks: list[KnowledgeChunk],
    ) -> dict[str, object]:
        """Build DTOs without writing to a Haystack DocumentStore."""
        _ = [
            _make_document(chunk.content, {"chunk_id": chunk.chunk_id, **chunk.metadata})
            for chunk in chunks
        ]
        return {"documents": documents, "chunks": chunks}


@component
class _EmbeddingComponent:
    """Batch-encode chunks and isolate failures by source document."""

    def __init__(self, embedder: BatchEmbedder) -> None:
        """Bind the existing embedding service or a hermetic fake encoder."""
        self._embedder = embedder

    @component.output_types(
        embedded=list[EmbeddedChunk],
        failed_document_ids=list[str],
    )
    def run(self, chunks: list[KnowledgeChunk]) -> dict[str, object]:
        """Encode a batch, retrying per document when a batch fails."""
        if not chunks:
            return {"embedded": [], "failed_document_ids": []}
        try:
            vectors = cast(
                list[list[float]],
                _run_async(self._embedder.encode([chunk.content for chunk in chunks])),
            )
            return {
                "embedded": _pair_embeddings(chunks, vectors),
                "failed_document_ids": [],
            }
        except (RuntimeError, ValueError, TypeError) as exc:
            log.warning("rag_embedding_batch_failed; isolating documents: %s", exc)

        grouped: dict[str, list[KnowledgeChunk]] = defaultdict(list)
        for chunk in chunks:
            grouped[chunk.document_id].append(chunk)
        embedded: list[EmbeddedChunk] = []
        failed: list[str] = []
        for document_id, document_chunks in grouped.items():
            try:
                vectors = cast(
                    list[list[float]],
                    _run_async(self._embedder.encode([chunk.content for chunk in document_chunks])),
                )
                embedded.extend(_pair_embeddings(document_chunks, vectors))
            except (RuntimeError, ValueError, TypeError) as exc:
                log.warning(
                    "rag_embedding_document_failed",
                    document_id=document_id,
                    error=str(exc),
                )
                failed.append(document_id)
        return {"embedded": embedded, "failed_document_ids": failed}


@component
class _VectorSinkComponent:
    """Write embeddings through VectorStorePort and register successful chunks."""

    def __init__(
        self,
        vector_store: VectorStorePort,
        registry: RagIndexRegistry,
        documents: dict[str, KnowledgeDocument],
    ) -> None:
        """Bind the backend-neutral vector store and registry."""
        self._vector_store = vector_store
        self._registry = registry
        self._documents = documents

    @component.output_types(
        indexed_chunk_ids=list[str],
        failed_document_ids=list[str],
    )
    def run(
        self,
        embedded: list[EmbeddedChunk],
        failed_document_ids: list[str],
        index_version: str,
    ) -> dict[str, object]:
        """Persist each chunk independently so one document cannot abort a batch."""
        indexed: list[str] = []
        failed = list(failed_document_ids)
        indexed_at = datetime.now(UTC).isoformat()
        for item in embedded:
            document = self._documents.get(item.chunk.document_id)
            if document is None:
                if item.chunk.document_id not in failed:
                    failed.append(item.chunk.document_id)
                continue
            try:
                _run_async(self._vector_store.upsert(item.chunk.chunk_id, item.embedding))
                _run_async(
                    self._registry.upsert(
                        item.chunk,
                        document,
                        indexed_at=indexed_at,
                        index_version=index_version,
                    )
                )
                indexed.append(item.chunk.chunk_id)
            except (RuntimeError, ValueError, TypeError) as exc:
                log.warning(
                    "rag_vector_chunk_failed",
                    chunk_id=item.chunk.chunk_id,
                    document_id=item.chunk.document_id,
                    error=str(exc),
                )
                if item.chunk.document_id not in failed:
                    failed.append(item.chunk.document_id)
        return {"indexed_chunk_ids": indexed, "failed_document_ids": failed}


class RagIndexingPipeline:
    """Run the Haystack indexing pipeline against the existing vector Port."""

    def __init__(
        self,
        vector_store: VectorStorePort,
        registry: RagIndexRegistry,
        embedder: BatchEmbedder,
    ) -> None:
        """Create the pipeline components; no persistent Haystack store is used."""
        self._vector_store = vector_store
        self._registry = registry
        self._embedder = embedder

    async def index(
        self,
        adapted_documents: Sequence[AdaptedDocument],
        *,
        index_version: str,
        incremental: bool = True,
        prune_source_document_ids: set[str] | None = None,
    ) -> IndexReport:
        """Index adapted documents with hash-based skipping and stale cleanup."""
        await self._registry.ensure_schema()
        candidates: list[AdaptedDocument] = []
        skipped: list[str] = []
        deleted: list[str] = []
        for adapted in adapted_documents:
            existing = {
                str(row["chunk_id"]): row
                for row in await self._registry.get_by_document(adapted.document.document_id)
            }
            current_ids = {chunk.chunk_id for chunk in adapted.chunks}
            for chunk_id, _row in existing.items():
                if chunk_id not in current_ids:
                    await self._vector_store.delete(chunk_id)
                    await self._registry.delete(chunk_id)
                    deleted.append(chunk_id)
            chunks_to_index: list[KnowledgeChunk] = []
            for chunk in adapted.chunks:
                old_hash = existing.get(chunk.chunk_id, {}).get("content_hash")
                if incremental and old_hash == _content_hash(chunk.content):
                    skipped.append(chunk.chunk_id)
                else:
                    chunks_to_index.append(chunk)
            if chunks_to_index:
                candidates.append(AdaptedDocument(adapted.document, tuple(chunks_to_index)))

        if prune_source_document_ids is not None:
            for row in await self._registry.list_source_documents():
                document_id = str(row["document_id"])
                if document_id not in prune_source_document_ids:
                    chunk_id = str(row["chunk_id"])
                    await self._vector_store.delete(chunk_id)
                    await self._registry.delete(chunk_id)
                    deleted.append(chunk_id)

        if not candidates:
            return IndexReport(skipped_chunk_ids=tuple(skipped), deleted_chunk_ids=tuple(deleted))

        documents = {item.document.document_id: item.document for item in candidates}
        chunks = [chunk for item in candidates for chunk in item.chunks]
        pipeline = self._build_pipeline(documents)
        result = await asyncio.to_thread(
            self._run_pipeline,
            pipeline,
            documents,
            chunks,
            index_version,
        )
        sink_result = result.get("sink", {})
        if not isinstance(sink_result, dict):
            sink_result = {}
        indexed_values = sink_result.get("indexed_chunk_ids", [])
        failed_values = sink_result.get("failed_document_ids", [])
        indexed_ids = tuple(str(value) for value in cast(list[object], indexed_values))
        failed_ids = tuple(str(value) for value in cast(list[object], failed_values))
        return IndexReport(
            indexed_chunk_ids=indexed_ids,
            skipped_chunk_ids=tuple(skipped),
            deleted_chunk_ids=tuple(deleted),
            failed_document_ids=failed_ids,
        )

    async def prune_source_documents(self, active_document_ids: set[str]) -> tuple[str, ...]:
        """Delete source-data vectors that have rolled outside the active window."""
        await self._registry.ensure_schema()
        deleted: list[str] = []
        for row in await self._registry.list_source_documents():
            document_id = str(row["document_id"])
            if document_id in active_document_ids:
                continue
            chunk_id = str(row["chunk_id"])
            await self._vector_store.delete(chunk_id)
            await self._registry.delete(chunk_id)
            deleted.append(chunk_id)
        return tuple(deleted)

    def _build_pipeline(self, documents: dict[str, KnowledgeDocument]) -> _PipelineLike:
        """Build a three-component in-memory Haystack graph."""
        pipeline = _new_pipeline()
        pipeline.add_component("source", _SourceComponent())
        pipeline.add_component("embedder", _EmbeddingComponent(self._embedder))
        pipeline.add_component(
            "sink",
            _VectorSinkComponent(self._vector_store, self._registry, documents),
        )
        pipeline.connect("source.chunks", "embedder.chunks")
        pipeline.connect("embedder.embedded", "sink.embedded")
        pipeline.connect("embedder.failed_document_ids", "sink.failed_document_ids")
        return pipeline

    @staticmethod
    def _run_pipeline(
        pipeline: _PipelineLike,
        documents: dict[str, KnowledgeDocument],
        chunks: list[KnowledgeChunk],
        index_version: str,
    ) -> dict[str, dict[str, object]]:
        """Invoke Haystack's synchronous run inside a worker thread."""
        run = pipeline.run
        value = run(
            {
                "source": {
                    "documents": list(documents.values()),
                    "chunks": chunks,
                },
                "sink": {"index_version": index_version},
            }
        )
        if not isinstance(value, dict):
            raise TypeError("Haystack pipeline returned a non-mapping result")
        raw_sink = value.get("sink", {})
        if not isinstance(raw_sink, dict):
            raw_sink = {}
        return {"sink": cast(dict[str, object], raw_sink)}


def _pair_embeddings(
    chunks: Sequence[KnowledgeChunk], vectors: Sequence[Sequence[float]]
) -> list[EmbeddedChunk]:
    """Validate batch cardinality and convert vectors to immutable tuples."""
    if len(chunks) != len(vectors):
        raise ValueError("embedding result count does not match chunk count")
    return [
        EmbeddedChunk(chunk, tuple(float(value) for value in vector))
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]


def _run_async(awaitable: object) -> object:
    """Run an awaitable from a synchronous Haystack component thread."""
    if not inspect.isawaitable(awaitable):
        return awaitable
    return asyncio.run(cast(Coroutine[object, object, object], awaitable))


def _content_hash(content: str) -> str:
    """Hash a chunk's normalized content for incremental indexing."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


__all__ = [
    "BatchEmbedder",
    "EmbeddedChunk",
    "IndexReport",
    "RagIndexRegistry",
    "RagIndexingPipeline",
]
