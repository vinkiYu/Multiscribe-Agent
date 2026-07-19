"""Optional lazy sentence-transformer embedding service."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import importlib.util
import math
from collections.abc import Callable, Sequence
from typing import Protocol, cast


class EmbeddingUnavailableError(RuntimeError):
    """Raised when the optional embedding runtime cannot be loaded."""


class _Encoder(Protocol):
    """Minimal sentence-transformer interface needed by this wrapper."""

    def encode(
        self, texts: list[str], *, normalize_embeddings: bool
    ) -> Sequence[Sequence[float]]: ...


class EmbeddingService:
    """Cache normalized 384-dimensional embeddings behind a lazy optional import."""

    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    DIM = 384

    def __init__(self, encoder: object | None = None) -> None:
        """Accept a test encoder or defer optional model loading until encoding."""
        self._encoder = encoder
        self._cache: dict[str, list[float]] = {}

    @staticmethod
    def is_available() -> bool:
        """Return whether the optional sentence-transformers package is installed."""
        return importlib.util.find_spec("sentence_transformers") is not None

    async def encode(self, texts: list[str]) -> list[list[float]]:
        """Return normalized vectors in input order, reusing content-hash cache entries."""
        missing = [
            text for text in texts if hashlib.sha256(text.encode()).hexdigest() not in self._cache
        ]
        if missing:
            values = await asyncio.to_thread(self._encode_sync, missing)
            for text, vector in zip(missing, values, strict=True):
                self._cache[hashlib.sha256(text.encode()).hexdigest()] = _normalize(vector)
        return [self._cache[hashlib.sha256(text.encode()).hexdigest()] for text in texts]

    async def encode_one(self, text: str) -> list[float]:
        """Encode one text item."""
        return (await self.encode([text]))[0]

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        """Load the optional model and coerce its output to plain floats."""
        if self._encoder is None:
            if not self.is_available():
                raise EmbeddingUnavailableError("sentence-transformers is unavailable")
            try:
                module = importlib.import_module("sentence_transformers")
                encoder_factory = cast(
                    Callable[[str], _Encoder],
                    module.__dict__["SentenceTransformer"],
                )
            except ImportError as exc:
                raise EmbeddingUnavailableError("sentence-transformers is unavailable") from exc
            self._encoder = encoder_factory(self.MODEL_NAME)
        if not hasattr(self._encoder, "encode"):
            raise EmbeddingUnavailableError("embedding encoder has no encode method")
        encoder = cast(_Encoder, self._encoder)
        raw = encoder.encode(texts, normalize_embeddings=True)
        return [[float(value) for value in row] for row in raw]

    @staticmethod
    def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
        """Return cosine similarity for equal-length vectors."""
        if len(a) != len(b) or not a or not b:
            return 0.0
        denominator = math.sqrt(
            sum(value * value for value in a) * sum(value * value for value in b)
        )
        return (
            sum(left * right for left, right in zip(a, b, strict=True)) / denominator
            if denominator
            else 0.0
        )


def _normalize(vector: Sequence[float]) -> list[float]:
    """Return an L2-normalized plain float vector."""
    magnitude = math.sqrt(sum(value * value for value in vector))
    return (
        [float(value) / magnitude for value in vector]
        if magnitude
        else [float(value) for value in vector]
    )
