"""Optional benchmark for Harness context trimming."""

import pytest

pytest.importorskip("pytest_benchmark")

from multiscribe_agent.agents.context import HarnessContext


@pytest.mark.benchmark
def test_context_trim_with_100_messages(benchmark) -> None:
    """Trimming a 100-message context remains a bounded hot-path operation."""
    context = HarnessContext("system prompt", token_budget=10_000)
    for index in range(100):
        context.add_user(f"message number {index} " * 20)
    benchmark(context.trim_if_needed)
