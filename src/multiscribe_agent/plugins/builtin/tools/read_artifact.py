"""Tool for retrieving compressed tool-result artifacts on demand."""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from multiscribe_agent.agents.artifacts import InMemoryArtifactStore
from multiscribe_agent.domain.models import PluginMetadata
from multiscribe_agent.plugins.base import BaseTool

DEFAULT_LIMIT = 8_000
MAX_LIMIT = 50_000


class ReadArtifactTool(BaseTool):
    """Read one bounded slice of a compressed tool result from the current run."""

    id: ClassVar[str] = "read_artifact"
    name: ClassVar[str] = "read_artifact"
    description: ClassVar[str] = (
        "Retrieve a bounded slice of a compressed tool result by its artifact reference."
    )
    is_builtin: ClassVar[bool] = True
    parameters: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "artifact_ref": {"type": "string"},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_LIMIT,
                "default": DEFAULT_LIMIT,
            },
        },
        "required": ["artifact_ref"],
        "additionalProperties": False,
    }
    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id=id,
        type="tool",
        name="Read Artifact",
        description=description,
        icon="file-search",
        config_fields=[],
        is_builtin=True,
    )

    def __init__(self, store: InMemoryArtifactStore | None = None) -> None:
        """Optionally inject a store; production resolves the current run store."""
        self._store = store

    async def handler(self, args: Mapping[str, object]) -> object:
        """Return one artifact page or a non-fatal error for unavailable content."""
        artifact_ref = args.get("artifact_ref")
        if not isinstance(artifact_ref, str) or not artifact_ref.strip():
            return "Error: artifact_ref must be a non-empty string"
        offset = self._integer_argument(args.get("offset"), default=0, minimum=0)
        if offset is None:
            return "Error: offset must be a non-negative integer"
        limit = self._integer_argument(args.get("limit"), default=DEFAULT_LIMIT, minimum=1)
        if limit is None or limit > MAX_LIMIT:
            return f"Error: limit must be an integer between 1 and {MAX_LIMIT}"

        store = self._store or InMemoryArtifactStore.current()
        if store is None:
            return "Error: no artifact store is available for this Agent run"
        content = store.get(artifact_ref, offset=offset, limit=limit)
        if content is None:
            return f"Error: artifact '{artifact_ref}' was not found or has expired"
        return {
            "artifact_ref": artifact_ref,
            "offset": offset,
            "limit": limit,
            "returned_chars": len(content),
            "content": content,
        }

    @staticmethod
    def _integer_argument(value: object, *, default: int, minimum: int) -> int | None:
        if value is None:
            return default
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            return None
        return value
