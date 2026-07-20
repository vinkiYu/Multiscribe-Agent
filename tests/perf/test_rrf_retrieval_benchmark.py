"""Optional benchmark for reciprocal-rank fusion."""

import pytest

pytest.importorskip("pytest_benchmark")

from multiscribe_agent.knowledge.retriever import _add_rrf


@pytest.mark.benchmark
def test_rrf_fusion_100_candidates(benchmark) -> None:
    """RRF fusion of two 100-candidate lists remains inexpensive."""
    first = [f"first-{index}" for index in range(100)]
    second = [f"second-{index}" for index in range(100)]

    def fuse() -> None:
        scores: dict[str, float] = {}
        sources: dict[str, list[str]] = {}
        _add_rrf(scores, sources, first, "fts", 1.0)
        _add_rrf(scores, sources, second, "vector", 1.0)

    benchmark(fuse)
