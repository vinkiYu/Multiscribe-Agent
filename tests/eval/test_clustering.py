"""Tests for the embedding/kmeans clustering fallback chain (P64.2 T11)."""

from __future__ import annotations

from pathlib import Path

from multiscribe_agent.eval.clustering import (
    EmbeddingClient,
    cosine,
    kmeans,
    tfidf_vectors,
)


def test_tfidf_vectors_shape_and_self_similarity() -> None:
    vectors = tfidf_vectors(["LLM agent framework release", "weather report rain"])
    assert len(vectors) == 2
    assert len(vectors[0]) == len(vectors[1])
    assert cosine(vectors[0], vectors[0]) > 0.99
    assert cosine(vectors[0], vectors[1]) < 0.2


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
    texts = llm_texts + weather_texts
    vectors = tfidf_vectors(texts)
    result = kmeans(vectors, k=2, seed=64)
    labels = set(result.labels[:3])
    other = set(result.labels[3:])
    assert labels.isdisjoint(other), result.labels


def test_kmeans_deterministic_seed() -> None:
    texts = [f"agent llm release number {i}" for i in range(6)] + [
        f"weather rain storm {i}" for i in range(6)
    ]
    vectors = tfidf_vectors(texts)
    first = kmeans(vectors, k=2, seed=64)
    second = kmeans(vectors, k=2, seed=64)
    assert first.labels == second.labels


def test_embedding_client_without_config_falls_back(tmp_path: Path) -> None:
    """No base URL/key configured: embed() returns TF-IDF vectors instead."""
    import asyncio

    client = EmbeddingClient(base_url="", api_key="", cache_dir=tmp_path)
    vectors = asyncio.run(client.embed(["agent llm", "weather rain"]))
    assert len(vectors) == 2
    assert vectors[0]  # non-empty fallback vector


def test_probe_unreachable_endpoint_returns_false(tmp_path: Path) -> None:
    import asyncio

    client = EmbeddingClient(
        base_url="https://invalid.invalid.test/v1",
        api_key="sk-test",
        cache_dir=tmp_path,
    )
    assert asyncio.run(client.probe()) is False
