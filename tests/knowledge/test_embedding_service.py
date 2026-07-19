"""Coverage for injected optional embedding service behavior."""

import pytest

from multiscribe_agent.knowledge.embedding_service import (
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
    service = EmbeddingService(encoder)

    first = await service.encode_one("alpha")
    second = await service.encode_one("alpha")

    assert first == second
    assert encoder.calls == 1
    assert EmbeddingService.cosine_similarity(first, second) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_embedding_service_reports_missing_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unavailable optional runtime raises without loading a model."""
    monkeypatch.setattr(EmbeddingService, "is_available", staticmethod(lambda: False))

    service = EmbeddingService()
    with pytest.raises(EmbeddingUnavailableError):
        await service.encode_one("alpha")
