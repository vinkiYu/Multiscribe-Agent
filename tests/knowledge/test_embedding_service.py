"""Coverage for injected optional embedding service behavior."""

import pytest

from multiscribe_agent.knowledge.embedding_service import (
    EmbeddingDimensionError,
    EmbeddingService,
    EmbeddingUnavailableError,
)


class FakeEncoder:
    """Return deterministic vectors and expose batch-call count."""

    def __init__(self) -> None:
        self.calls = 0

    def encode(self, texts: list[str], *, normalize_embeddings: bool) -> list[list[float]]:
        """Return simple fixed-length test vectors."""
        del normalize_embeddings
        self.calls += 1
        return [[float(len(text)), 1.0] for text in texts]


@pytest.mark.asyncio
async def test_embedding_service_caches_and_normalizes_injected_encoder() -> None:
    """Repeated content does not invoke the injected encoder a second time."""
    encoder = FakeEncoder()
    service = EmbeddingService(encoder, dimension=2)

    first = await service.encode_one("alpha")
    second = await service.encode_one("alpha")

    assert first == second
    assert encoder.calls == 1
    assert EmbeddingService.cosine_similarity(first, second) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_embedding_service_rejects_wrong_dimension() -> None:
    """A configured embedding space never accepts a silently truncated vector."""
    with pytest.raises(EmbeddingDimensionError, match="expected 3"):
        await EmbeddingService(FakeEncoder(), dimension=3).encode_one("alpha")


@pytest.mark.asyncio
async def test_embedding_service_cache_is_bounded() -> None:
    """The content-hash cache evicts least-recently-used entries at its configured bound."""
    encoder = FakeEncoder()
    service = EmbeddingService(encoder, dimension=2, cache_size=2)

    await service.encode(["one", "two"])
    await service.encode_one("three")

    assert len(service._cache) == 2
    assert len(service._cache) <= service.cache_size
    await service.encode_one("one")
    assert encoder.calls == 3


@pytest.mark.asyncio
async def test_embedding_service_reports_missing_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unavailable optional runtime raises without loading a model."""
    monkeypatch.setattr(EmbeddingService, "is_available", staticmethod(lambda: False))

    service = EmbeddingService()
    with pytest.raises(EmbeddingUnavailableError):
        await service.encode_one("alpha")
