"""Adapters from the existing content stores to the P66 RAG contracts.

The adapter is deliberately kept above the frozen ``rag.models`` module.  It
knows how the legacy ``SourceData`` and ``KBDocument`` records are shaped, but
the indexing and later retrieval phases only consume ``KnowledgeDocument`` and
``KnowledgeChunk``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from multiscribe_agent.domain.models import KBChunk, KBDocument, SourceData
from multiscribe_agent.knowledge.chunking import split_text
from multiscribe_agent.rag.models import KnowledgeChunk, KnowledgeDocument

DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64


@dataclass(frozen=True, slots=True)
class AdaptedDocument:
    """A canonical document together with its indexable chunks."""

    document: KnowledgeDocument
    chunks: tuple[KnowledgeChunk, ...]


class RagDocumentAdapter:
    """Convert legacy source records and KB records into RAG documents."""

    def __init__(
        self,
        *,
        user_id: str = "default",
        source_window_days: int = 7,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        """Configure ownership, source freshness, and KB sliding-window sizing."""
        if not user_id.strip():
            raise ValueError("user_id must not be empty")
        if source_window_days < 0:
            raise ValueError("source_window_days must be non-negative")
        self.user_id = user_id
        self.source_window_days = source_window_days
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def adapt_source_data(
        self, row: SourceData, *, now: datetime | None = None
    ) -> AdaptedDocument | None:
        """Adapt one recent SourceData row into one document and one chunk.

        SourceData entries are intentionally not split: a news item is already
        short and splitting it would consume extra retrieval slots without
        adding useful locality.
        """
        document = from_source_data(
            row,
            user_id=self.user_id,
            window_days=self.source_window_days,
            now=now,
        )
        if document is None:
            return None
        content = _source_content(row)
        chunk = KnowledgeChunk(
            chunk_id=f"{document.document_id}:0",
            document_id=document.document_id,
            content=content,
            index=0,
            metadata={
                "doc_type": "source_data",
                "source": row.source,
                "category": row.category,
                "url": row.url,
                "user_id": self.user_id,
                "char_start": 0,
                "char_end": len(content),
            },
        )
        return AdaptedDocument(document=document, chunks=(chunk,))

    def adapt_kb_document(
        self,
        document: KBDocument,
        chunks: list[KBChunk] | None = None,
    ) -> AdaptedDocument:
        """Adapt one KB document using persisted chunks or sliding-window text."""
        return adapt_kb_document(
            document,
            chunks,
            user_id=self.user_id,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )


def from_source_data(
    row: SourceData,
    *,
    user_id: str,
    window_days: int,
    now: datetime | None = None,
) -> KnowledgeDocument | None:
    """Map a SourceData row, returning ``None`` when it is outside the window."""
    if not _within_source_window(row.published_date, window_days, now=now):
        return None
    content = _source_content(row)
    return KnowledgeDocument(
        document_id=f"source_data:{row.id}",
        doc_type="source_data",
        title=row.title or row.url,
        url=row.url or f"source://{row.id}",
        source=row.source or row.adapter_name,
        category=row.category or "uncategorized",
        published_at=row.published_date or None,
        user_id=user_id,
        content_hash=_sha256(content),
    )


def adapt_kb_document(
    document: KBDocument,
    chunks: list[KBChunk] | None = None,
    *,
    user_id: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> AdaptedDocument:
    """Map a KBDocument and create stable sliding-window chunks.

    When persisted KBChunk rows are supplied, their content and order are
    retained.  Otherwise the adapter uses the best available text field from
    the JSON metadata and applies the same ``split_text`` semantics used by
    the existing KB service.
    """
    source_chunks = chunks or []
    if source_chunks:
        chunk_values = [
            _knowledge_chunk_from_existing(document.id, item, user_id=user_id)
            for item in sorted(source_chunks, key=lambda value: (value.index, value.id))
        ]
    else:
        raw_text = _kb_text(document)
        chunk_values = [
            KnowledgeChunk(
                chunk_id=f"kb:{document.id}:{item.index}",
                document_id=f"kb:{document.id}",
                content=item.text,
                index=item.index,
                metadata={
                    "doc_type": "kb",
                    "source": "knowledge_base",
                    "category": document.category_id or "uncategorized",
                    "user_id": user_id,
                    "char_start": item.char_start,
                    "char_end": item.char_end,
                },
            )
            for item in split_text(
                raw_text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        ]

    content_hash = _sha256("\n".join(item.content for item in chunk_values))
    canonical_id = f"kb:{document.id}"
    canonical = KnowledgeDocument(
        document_id=canonical_id,
        doc_type="kb",
        title=document.name or document.file_name or document.id,
        url=f"kb://{document.id}",
        source="knowledge_base",
        category=document.category_id or "uncategorized",
        published_at=None,
        user_id=user_id,
        content_hash=content_hash,
    )
    return AdaptedDocument(document=canonical, chunks=tuple(chunk_values))


def from_kb_document(
    document: KBDocument,
    chunks: list[KBChunk] | None = None,
    *,
    user_id: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> KnowledgeDocument:
    """Return only the canonical KB document for callers that do not need chunks."""
    return adapt_kb_document(
        document,
        chunks,
        user_id=user_id,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    ).document


def _knowledge_chunk_from_existing(
    document_id: str,
    item: KBChunk,
    *,
    user_id: str,
) -> KnowledgeChunk:
    """Preserve a persisted KBChunk while filling the P66 metadata envelope."""
    metadata: dict[str, object] = dict(item.metadata)
    metadata.update(
        {
            "doc_type": "kb",
            "source": "knowledge_base",
            "user_id": user_id,
        }
    )
    metadata.setdefault("char_start", 0)
    metadata.setdefault("char_end", len(item.content))
    return KnowledgeChunk(
        chunk_id=f"kb:{document_id}:{item.index}",
        document_id=f"kb:{document_id}",
        content=item.content,
        index=item.index,
        metadata=metadata,
    )


def _source_content(row: SourceData) -> str:
    """Combine the title and description into one stable index payload."""
    title = row.title.strip()
    description = row.description.strip()
    return "\n\n".join(value for value in (title, description) if value) or row.url


def _kb_text(document: KBDocument) -> str:
    """Extract document text from the legacy JSON blob without changing storage."""
    for key in ("content", "body", "text"):
        value = document.metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return document.summary or document.name or document.file_name or document.id


def _within_source_window(
    published_at: str,
    window_days: int,
    *,
    now: datetime | None,
) -> bool:
    """Return whether a publication timestamp belongs to the configured window."""
    if window_days < 0:
        raise ValueError("window_days must be non-negative")
    if not published_at:
        return True
    try:
        value = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    return value >= reference - timedelta(days=window_days)


def _sha256(value: str) -> str:
    """Return the content hash used by the incremental indexer."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "AdaptedDocument",
    "RagDocumentAdapter",
    "adapt_kb_document",
    "from_kb_document",
    "from_source_data",
]
