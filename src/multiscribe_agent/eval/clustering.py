"""Deterministic TF-IDF failure clustering (P64.3 P3).

Decision recorded 2026-08-15:
- relay ``text-embedding-3-small`` returned HTTP 404 model_not_found;
- P64.2's specified local ``paraphrase-multilingual-MiniMax`` repository
  returned RepositoryNotFoundError;
- 36 failed samples already produced four usable clusters with TF-IDF.

TF-IDF is intentionally the fixed P64.3 backend. Its vocabulary is generated
per batch, so vectors cannot safely be reused as per-text embedding-cache
entries; ``data/eval/embedding_cache`` is not read or written by this module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EMBEDDING_BACKEND = "tfidf-char-ngram"


def tfidf_vectors(texts: list[str]) -> list[list[float]]:
    """Build zero-dependency, batch-relative character bigram/trigram vectors."""
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
    """Return cosine similarity after requiring compatible vector dimensions."""
    if len(a) != len(b):
        raise ValueError("cannot compare vectors with different dimensions")
    return sum(x * y for x, y in zip(a, b, strict=True))


@dataclass(frozen=True, slots=True)
class ClusterResult:
    """Deterministic k-means output over one batch of failure texts."""

    labels: list[int]
    centroids: list[list[float]]
    k: int


def kmeans(
    vectors: list[list[float]], k: int, iterations: int = 50, seed: int = 64
) -> ClusterResult:
    """Run cosine k-means with a deterministic LCG seed over same-size vectors."""
    if not vectors:
        return ClusterResult(labels=[], centroids=[], k=k)
    dimensions = len(vectors[0])
    if any(len(vector) != dimensions for vector in vectors):
        raise ValueError("kmeans requires vectors with identical dimensions")
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
                sum(member[dim] for member in members) / size for dim in range(dimensions)
            ]
            centroids[cluster] = _normalize(centroids[cluster])
        if not changed:
            break
    return ClusterResult(labels=labels, centroids=centroids, k=k)


__all__ = ["EMBEDDING_BACKEND", "ClusterResult", "cosine", "kmeans", "tfidf_vectors"]
