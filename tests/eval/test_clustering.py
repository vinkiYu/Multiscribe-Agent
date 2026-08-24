"""Tests for the fixed P64.3 offline TF-IDF clustering backend."""

from __future__ import annotations

import pytest

from multiscribe_agent.eval.clustering import EMBEDDING_BACKEND, cosine, kmeans, tfidf_vectors


def test_tfidf_vectors_shape_and_self_similarity() -> None:
    vectors = tfidf_vectors(["LLM agent framework release", "weather report rain"])
    assert len(vectors) == 2
    assert len(vectors[0]) == len(vectors[1])
    assert cosine(vectors[0], vectors[0]) > 0.99
    assert cosine(vectors[0], vectors[1]) < 0.2


def test_fixed_backend_is_explicit_and_offline() -> None:
    """P64.3's fixed backend has no provider/client or HTTP dependency."""
    assert EMBEDDING_BACKEND == "tfidf-char-ngram"


def test_kmeans_groups_similar_texts() -> None:
    llm_texts = [
        "OpenAI releases GPT agent framework",
        "LLM agent benchmark evaluation released",
        "Agent framework for LLM planning released",
    ]
    weather_texts = [
        "Heavy rain floods the coastal city",
        "Coastal weather forecast heavy storms",
        "Storm rain forecast city weather",
    ]
    vectors = tfidf_vectors(llm_texts + weather_texts)
    result = kmeans(vectors, k=2, seed=64)
    assert set(result.labels[:3]).isdisjoint(set(result.labels[3:])), result.labels


def test_kmeans_deterministic_seed() -> None:
    texts = [f"agent llm release number {i}" for i in range(6)] + [
        f"weather rain storm {i}" for i in range(6)
    ]
    vectors = tfidf_vectors(texts)
    assert kmeans(vectors, k=2, seed=64).labels == kmeans(vectors, k=2, seed=64).labels


def test_mixed_dimensions_fail_before_kmeans() -> None:
    with pytest.raises(ValueError, match="identical dimensions"):
        kmeans([[1.0, 0.0], [1.0]], k=2)


def test_cosine_rejects_mixed_dimensions() -> None:
    with pytest.raises(ValueError, match="different dimensions"):
        cosine([1.0], [1.0, 0.0])
