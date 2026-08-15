"""Failure clustering with relay embeddings, cache, and a TF-IDF fallback (T11).

Embedding decision chain (docs/phases/P64.2 §T11):
1. relay ``text-embedding-3-small`` via the configured OpenAI-compatible endpoint
2. (not bundled) local sentence-transformers — would add a heavy dependency
3. zero-dependency character n-gram TF-IDF fallback, always available
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

import httpx

EMBEDDING_MODEL = "text-embedding-3-small"


class EmbeddingClient:
    """Call the OpenAI-compatible /embeddings endpoint with an on-disk cache."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        cache_dir: Path | None = None,
        model: str = EMBEDDING_MODEL,
    ) -> None:
        self.base_url = (base_url or os.environ.get("OPENAI_API_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model
        self.cache_dir = cache_dir
        if cache_dir is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)

    async def probe(self) -> bool:
        """Return True when the endpoint answers a one-text embedding request."""
        if not self.base_url or not self.api_key:
            return False
        try:
            vectors = await self._fetch(["probe"])
            return bool(vectors and vectors[0])
        except (httpx.HTTPError, OSError, ValueError, KeyError):
            return False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts, reusing cached vectors; falls back to TF-IDF on failure."""
        if not self.base_url or not self.api_key:
            return tfidf_vectors(texts)
        vectors: list[list[float] | None] = [None] * len(texts)
        missing: list[int] = []
        for index, text in enumerate(texts):
            cached = self._cache_get(text)
            if cached is None:
                missing.append(index)
            else:
                vectors[index] = cached
        if missing:
            try:
                fetched = await self._fetch([texts[i] for i in missing])
                for position, index in enumerate(missing):
                    vectors[index] = fetched[position]
                    self._cache_put(texts[index], fetched[position])
            except (httpx.HTTPError, OSError, ValueError, KeyError):
                fallback = tfidf_vectors([texts[i] for i in missing])
                for position, index in enumerate(missing):
                    vectors[index] = fallback[position]
        return [vector if vector is not None else [] for vector in vectors]

    async def _fetch(self, texts: list[str]) -> list[list[float]]:
        request = {"model": self.model, "input": texts}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            response = await client.post(
                f"{self.base_url}/embeddings", json=request, headers=headers
            )
            response.raise_for_status()
            payload: dict[str, object] = response.json()
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise ValueError("embeddings response missing data")
        vectors: list[list[float]] = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("embedding"), list):
                raise ValueError("embeddings response missing embedding")
            vectors.append([float(value) for value in row["embedding"]])
        return vectors

    def _cache_key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model}|{text}".encode()).hexdigest()

    def _cache_get(self, text: str) -> list[float] | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / f"{self._cache_key(text)}.json"
        if not path.exists():
            return None
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            return [float(value) for value in loaded]
        return None

    def _cache_put(self, text: str, vector: list[float]) -> None:
        if self.cache_dir is None:
            return
        path = self.cache_dir / f"{self._cache_key(text)}.json"
        path.write_text(json.dumps(vector), encoding="utf-8")


def tfidf_vectors(texts: list[str]) -> list[list[float]]:
    """Zero-dependency character bigram TF-IDF fallback."""
    if not texts:
        return []
    documents = [_char_ngrams(text) for text in texts]
    vocabulary: dict[str, int] = {}
    for counts in documents:
        for token in counts:
            vocabulary.setdefault(token, len(vocabulary))
    document_count = len(documents)
    inverse_document_frequency = {
        token: math.log((document_count + 1) / (1 + sum(1 for c in documents if token in c))) + 1.0
        for token in vocabulary
    }
    vectors: list[list[float]] = []
    for counts in documents:
        vector = [0.0] * len(vocabulary)
        total = sum(counts.values()) or 1
        for token, count in counts.items():
            index = vocabulary[token]
            vector[index] = (count / total) * inverse_document_frequency[token]
        vectors.append(_normalize(vector))
    return vectors


def _char_ngrams(text: str) -> dict[str, int]:
    cleaned = "".join(character.casefold() if character.isalnum() else " " for character in text)
    counts: dict[str, int] = {}
    for token in cleaned.split():
        padded = f"^{token}$"
        for size in (2, 3):
            for index in range(len(padded) - size + 1):
                gram = padded[index : index + size]
                counts[gram] = counts.get(gram, 0) + 1
    return counts


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True))


@dataclass(frozen=True, slots=True)
class ClusterResult:
    """K-means clustering output over failure texts."""

    labels: list[int]
    centroids: list[list[float]]
    k: int


def kmeans(
    vectors: list[list[float]], k: int, iterations: int = 50, seed: int = 64
) -> ClusterResult:
    """Cosine k-means with deterministic seeding (multiplier LCG)."""
    if not vectors:
        return ClusterResult(labels=[], centroids=[], k=k)
    k = min(k, len(vectors))
    state = seed

    def rand_below(bound: int) -> int:
        nonlocal state
        state = (state * 1103515245 + 12345) % (2**31)
        return state % bound

    centroids = [vectors[rand_below(len(vectors))][:] for _ in range(k)]
    labels = [0] * len(vectors)
    for _ in range(iterations):
        changed = False
        for index, vector in enumerate(vectors):
            best, best_similarity = 0, -2.0
            for cluster, centroid in enumerate(centroids):
                similarity = cosine(vector, centroid)
                if similarity > best_similarity:
                    best, best_similarity = cluster, similarity
            if labels[index] != best:
                labels[index] = best
                changed = True
        for cluster in range(k):
            members = [vectors[i] for i, label in enumerate(labels) if label == cluster]
            if not members:
                centroids[cluster] = vectors[rand_below(len(vectors))][:]
                continue
            size = len(members)
            centroids[cluster] = [
                sum(member[dim] for member in members) / size
                for dim in range(len(members[0]))
            ]
            centroids[cluster] = _normalize(centroids[cluster])
        if not changed:
            break
    return ClusterResult(labels=labels, centroids=centroids, k=k)


__all__ = [
    "EMBEDDING_MODEL",
    "ClusterResult",
    "EmbeddingClient",
    "cosine",
    "kmeans",
    "tfidf_vectors",
]
