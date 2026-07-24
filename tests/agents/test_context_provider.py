"""Observability coverage for best-effort Agent context retrieval."""

from __future__ import annotations

import pytest

import multiscribe_agent.agents.context_provider as context_provider_module
from multiscribe_agent.agents.context_provider import MemoryKnowledgeContextProvider


class _FailingMemory:
    async def search_entries(self, query: str, limit: int) -> list[object]:
        del query, limit
        raise TimeoutError("memory lookup timed out")


class _CapturingLog:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def warning(self, event: str, **kwargs: object) -> None:
        self.calls.append((event, kwargs))


@pytest.mark.asyncio
async def test_memory_failure_is_logged_and_keeps_retrieval_degraded(monkeypatch) -> None:
    """Memory failures remain non-fatal but leave a safe structured diagnostic."""
    log = _CapturingLog()
    monkeypatch.setattr(context_provider_module, "log", log)
    provider = MemoryKnowledgeContextProvider(_FailingMemory(), None)

    result = await provider.retrieve("sensitive query that should be bounded", agent_id="agent-1")

    assert result.memories == []
    assert result.reasons == ["memory:degraded"]
    assert log.calls == [
        (
            "context_provider_memory_degraded",
            {
                "query_prefix": "sensitive query that should be bounded",
                "error_type": "TimeoutError",
                "error_message": "memory lookup timed out",
            },
        )
    ]
