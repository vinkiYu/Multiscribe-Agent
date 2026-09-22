"""Stable, backend-neutral contracts for the P66 RAG subsystem.

The models in this module are intentionally independent from Haystack, the
database layer, and the existing KB implementation.  P66.1 freezes the
contract; later phases may adapt existing KBDocument/KBChunk and SourceData
records into these models without changing Agent-facing code.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _RagModel(BaseModel):
    """Base model for mutable JSON-compatible RAG contracts."""

    model_config = ConfigDict(frozen=False)


def _required_text(value: str, field_name: str) -> str:
    """Reject blank identifiers and required textual metadata."""
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


class KnowledgeDocument(_RagModel):
    """Canonical document from the KB or the SourceData stream."""

    document_id: str
    doc_type: Literal["kb", "source_data"]
    title: str
    url: str
    source: str
    category: str
    published_at: str | None = None
    user_id: str
    content_hash: str
    indexed_at: str | None = None

    @field_validator(
        "document_id",
        "title",
        "url",
        "source",
        "category",
        "user_id",
        "content_hash",
    )
    @classmethod
    def _validate_required_fields(cls, value: str, info: object) -> str:
        """Keep identifiers and source metadata usable as retrieval keys."""
        field_name = getattr(info, "field_name", "field")
        return _required_text(value, str(field_name))


class KnowledgeChunk(_RagModel):
    """One indexable chunk belonging to a canonical document."""

    chunk_id: str
    document_id: str
    content: str
    index: int = Field(ge=0)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("chunk_id", "document_id", "content")
    @classmethod
    def _validate_required_fields(cls, value: str, info: object) -> str:
        """Reject empty chunk identifiers, owners, and payloads."""
        field_name = getattr(info, "field_name", "field")
        return _required_text(value, str(field_name))


class RetrievalScope(_RagModel):
    """Retrieval visibility and optional metadata filters.

    ``user_id`` is the hard isolation boundary.  ``agent_id`` is deliberately
    optional: a value filters to an Agent's knowledge, while ``None`` means
    the caller may search all documents owned by the user.
    """

    user_id: str
    agent_id: str | None = None
    categories: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    time_from: str | None = None
    time_to: str | None = None
    doc_types: list[Literal["kb", "source_data"]] = Field(default_factory=list)

    @field_validator("user_id")
    @classmethod
    def _validate_user_id(cls, value: str) -> str:
        """Require a concrete user boundary for every retrieval."""
        return _required_text(value, "user_id")


class RetrievedEvidence(_RagModel):
    """A ranked result with complete document provenance for Agent context."""

    evidence_id: str
    chunk: KnowledgeChunk
    document: KnowledgeDocument
    score: float
    retrieval_source: Literal["bm25", "vector", "hybrid"]
    scope: RetrievalScope

    @field_validator("evidence_id")
    @classmethod
    def _validate_evidence_id(cls, value: str) -> str:
        """Reject evidence without a stable identity."""
        return _required_text(value, "evidence_id")


class RagCapabilities(_RagModel):
    """Runtime feature flags exposed without leaking backend details."""

    vector_enabled: bool = False
    embedding_enabled: bool = False
    fts_enabled: bool = True

    @property
    def degraded(self) -> bool:
        """Return whether retrieval must fall back to keyword search."""
        return not (self.vector_enabled and self.embedding_enabled)

    def as_dict(self) -> dict[str, bool]:
        """Return API-safe capability names compatible with KBCapabilities."""
        return {
            "vector": self.vector_enabled,
            "embedding": self.embedding_enabled,
            "fts": self.fts_enabled,
            "degraded": self.degraded,
        }
