"""Optional cross-encoder reranking for the P66 RAG retrieval boundary."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
from collections.abc import Sequence
from typing import Protocol, cast

from multiscribe_agent.rag.models import RetrievedEvidence


class RerankerUnavailableError(RuntimeError):
    """Raised when the optional cross-encoder runtime cannot be loaded."""


class RerankerPort(Protocol):
    """Rank already-retrieved evidence for one query."""

    async def rerank(
        self, query: str, evidence: list[RetrievedEvidence], *, top_k: int
    ) -> list[RetrievedEvidence]:
        """Return at most ``top_k`` evidence records in reranked order."""
        ...


class _CrossEncoder(Protocol):
    """Minimal sentence-transformers CrossEncoder surface used by this adapter."""

    def predict(self, sentences: list[tuple[str, str]]) -> Sequence[float]:
        """Return one relevance score per query/document pair."""
        ...


class CrossEncoderReranker:
    """Lazy, optional BGE cross-encoder that keeps model loading off the hot path."""

    MODEL_NAME = "BAAI/bge-reranker-v2-m3"

    def __init__(self, model_name: str = MODEL_NAME, model: object | None = None) -> None:
        """Configure the model without loading it until the first rerank call."""
        if not model_name.strip():
            raise ValueError("model_name must not be empty")
        self.model_name = model_name.strip()
        self._model = model

    @staticmethod
    def is_available() -> bool:
        """Return whether sentence-transformers is installed."""
        return importlib.util.find_spec("sentence_transformers") is not None

    async def rerank(
        self, query: str, evidence: list[RetrievedEvidence], *, top_k: int
    ) -> list[RetrievedEvidence]:
        """Score query/evidence pairs and return a deterministic descending ranking."""
        if top_k < 1 or not evidence:
            return []
        model = await asyncio.to_thread(self._load_model)
        pairs = [(query, item.chunk.content) for item in evidence]
        scores = await asyncio.to_thread(model.predict, pairs)
        values = [float(score) for score in scores]
        if len(values) != len(evidence):
            raise ValueError(
                f"reranker returned {len(values)} scores for {len(evidence)} evidence records"
            )
        ranked = [
            _with_rerank_score(item, score) for item, score in zip(evidence, values, strict=True)
        ]
        ranked.sort(key=lambda item: (-item.score, item.evidence_id))
        return ranked[:top_k]

    def _load_model(self) -> _CrossEncoder:
        """Load the optional cross-encoder exactly once in a worker thread."""
        if self._model is None:
            if not self.is_available():
                raise RerankerUnavailableError("sentence-transformers is unavailable")
            try:
                module = importlib.import_module("sentence_transformers")
                factory = cast(object, module.__dict__.get("CrossEncoder"))
            except ImportError as exc:
                raise RerankerUnavailableError("sentence-transformers is unavailable") from exc
            if not callable(factory):
                raise RerankerUnavailableError("sentence-transformers has no CrossEncoder")
            self._model = factory(self.model_name)
        if not hasattr(self._model, "predict"):
            raise RerankerUnavailableError("reranker model has no predict method")
        return cast(_CrossEncoder, self._model)


def _with_rerank_score(evidence: RetrievedEvidence, score: float) -> RetrievedEvidence:
    """Return evidence with validated reranker provenance."""
    return evidence.model_copy(
        update={
            "score": score,
            "retrieval_source": f"{evidence.retrieval_source}:reranked",
        }
    )


__all__ = [
    "CrossEncoderReranker",
    "RerankerPort",
    "RerankerUnavailableError",
]
