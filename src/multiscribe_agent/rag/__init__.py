"""Public contracts for the P66 retrieval-augmented generation subsystem."""

from multiscribe_agent.rag.adapter import AdaptedDocument, RagDocumentAdapter
from multiscribe_agent.rag.bm25 import Bm25Hit, RagBm25Retriever
from multiscribe_agent.rag.dense import DenseHit, RagDenseRetriever
from multiscribe_agent.rag.indexing import IndexReport, RagIndexingPipeline, RagIndexRegistry
from multiscribe_agent.rag.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    RagCapabilities,
    RetrievalScope,
    RetrievedEvidence,
)
from multiscribe_agent.rag.ports import RagServiceProtocol, RetrievalPort
from multiscribe_agent.rag.schema import RagChunksStore
from multiscribe_agent.rag.service import RagService, RuntimeRagCapabilities

__all__ = [
    "AdaptedDocument",
    "Bm25Hit",
    "DenseHit",
    "IndexReport",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "RagBm25Retriever",
    "RagCapabilities",
    "RagChunksStore",
    "RagDenseRetriever",
    "RagDocumentAdapter",
    "RagIndexRegistry",
    "RagIndexingPipeline",
    "RagService",
    "RagServiceProtocol",
    "RetrievalPort",
    "RetrievalScope",
    "RetrievedEvidence",
    "RuntimeRagCapabilities",
]
