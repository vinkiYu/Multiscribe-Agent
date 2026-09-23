"""Optional lazy sentence-transformer embedding service."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import importlib.util
import math
from collections import OrderedDict
from collections.abc import Callable, Sequence
from typing import Protocol, cast


class EmbeddingUnavailableError(RuntimeError):
    """Raised when the optional embedding runtime cannot be loaded."""


class EmbeddingDimensionError(ValueError):
    """Raised when an encoder returns vectors outside the configured space."""


class _Encoder(Protocol):
    """Minimal sentence-transformer interface needed by this wrapper."""

    def encode(
        self, texts: list[str], *, normalize_embeddings: bool
    ) -> Sequence[Sequence[float]]: ...


class EmbeddingService:
    """Cache normalized embeddings behind a configurable lazy optional import."""

    MODEL_NAME = "BAAI/bge-small-zh-v1.5"
    DIM = 512
    DEFAULT_CACHE_SIZE = 10_000

    def __init__(
        self,
        encoder: object | None = None,
        *,
        model_name: str = MODEL_NAME,
        dimension: int = DIM,
        cache_size: int = DEFAULT_CACHE_SIZE,
    ) -> None:
        """Accept an injected encoder or defer optional model loading until encoding."""
        if not model_name.strip():
            raise ValueError("model_name must not be empty")
        if dimension <= 0:
            raise ValueError("embedding dimension must be positive")
        if cache_size <= 0:
            raise ValueError("embedding cache size must be positive")
        self._encoder = encoder
        self.model_name = model_name.strip()
        self.dimension = dimension
        self.cache_size = cache_size
        self._cache: OrderedDict[str, list[float]] = OrderedDict()

    @staticmethod
    def is_available() -> bool:
        """Return whether the optional sentence-transformers package is installed."""
        return importlib.util.find_spec("sentence_transformers") is not None

    async def encode(self, texts: list[str]) -> list[list[float]]:
        """Return normalized vectors in input order, reusing content-hash cache entries."""
        missing: list[str] = []
        missing_hashes: set[str] = set()
        for text in texts:
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            if text_hash not in self._cache and text_hash not in missing_hashes:
                missing.append(text)
                missing_hashes.add(text_hash)
        if missing:
            values = await asyncio.to_thread(self._encode_sync, missing)
            for text, vector in zip(missing, values, strict=True):
                text_hash = hashlib.sha256(text.encode()).hexdigest()
                self._cache[text_hash] = _normalize(vector)
                self._cache.move_to_end(text_hash)
                while len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
        result: list[list[float]] = []
        for text in texts:
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            result.append(self._cache[text_hash])
            self._cache.move_to_end(text_hash)
        return result

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
            self._encoder = encoder_factory(self.model_name)
        if not hasattr(self._encoder, "encode"):
            raise EmbeddingUnavailableError("embedding encoder has no encode method")
        encoder = cast(_Encoder, self._encoder)
        raw = encoder.encode(texts, normalize_embeddings=True)
        vectors = [[float(value) for value in row] for row in raw]
        for vector in vectors:
            if len(vector) != self.dimension:
                raise EmbeddingDimensionError(
                    f"embedding model {self.model_name!r} returned {len(vector)} dimensions; "
                    f"expected {self.dimension}"
                )
        return vectors

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
