"""Tests for on-demand retrieval of compressed tool-result artifacts."""

from __future__ import annotations

import pytest

from multiscribe_agent.agents.artifacts import InMemoryArtifactStore
from multiscribe_agent.plugins.builtin.tools.read_artifact import ReadArtifactTool


@pytest.mark.asyncio
async def test_read_artifact_returns_content_from_injected_store() -> None:
    """A tool can recover a compressed result through its artifact reference."""
    store = InMemoryArtifactStore()
    artifact_ref = store.put("full tool result", "call-1")

    result = await ReadArtifactTool(store).handler({"artifact_ref": artifact_ref})

    assert result == {
        "artifact_ref": artifact_ref,
        "offset": 0,
        "limit": 8_000,
        "returned_chars": 16,
        "content": "full tool result",
    }


@pytest.mark.asyncio
async def test_read_artifact_paginates_and_uses_the_task_local_store() -> None:
    """Pagination limits output while the production default resolves the active run store."""
    store = InMemoryArtifactStore()
    artifact_ref = store.put("0123456789", "call-1")

    result = await ReadArtifactTool().handler(
        {"artifact_ref": artifact_ref, "offset": 3, "limit": 4}
    )

    assert result == {
        "artifact_ref": artifact_ref,
        "offset": 3,
        "limit": 4,
        "returned_chars": 4,
        "content": "3456",
    }
    assert store.list_artifacts() == [
        {
            "id": artifact_ref,
            "tool_call_id": "call-1",
            "created_at": pytest.approx(store.list_artifacts()[0]["created_at"]),
            "char_count": 10,
        }
    ]


@pytest.mark.asyncio
async def test_read_artifact_returns_non_fatal_error_for_missing_reference() -> None:
    """An expired or invalid reference cannot crash the surrounding Agent run."""
    result = await ReadArtifactTool(InMemoryArtifactStore()).handler({"artifact_ref": "missing"})

    assert result == "Error: artifact 'missing' was not found or has expired"
