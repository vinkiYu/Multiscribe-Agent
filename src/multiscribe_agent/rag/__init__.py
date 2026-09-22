"""Public contracts for the P66 retrieval-augmented generation subsystem."""

from multiscribe_agent.rag.adapter import AdaptedDocument, RagDocumentAdapter
from multiscribe_agent.rag.indexing import IndexReport, RagIndexingPipeline, RagIndexRegistry
from multiscribe_agent.rag.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    RagCapabilities,
    RetrievalScope,
    RetrievedEvidence,
)
from multiscribe_agent.rag.ports import RagServiceProtocol, RetrievalPort

__all__ = [
    "AdaptedDocument",
    "IndexReport",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "RagCapabilities",
    "RagDocumentAdapter",
    "RagIndexRegistry",
    "RagIndexingPipeline",
    "RagServiceProtocol",
    "RetrievalPort",
    "RetrievalScope",
    "RetrievedEvidence",
]
