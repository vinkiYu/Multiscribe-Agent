"""Bounded ephemeral artifacts for oversized tool results."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Artifact:
    id: str
    content: str
    tool_call_id: str
    created_at: float


class InMemoryArtifactStore:
    """Keep full results for one process with TTL and total-size bounds."""

    def __init__(self, *, max_chars: int = 1_000_000, ttl_seconds: float = 3600) -> None:
        self._max_chars = max_chars
        self._ttl = ttl_seconds
        self._items: dict[str, Artifact] = {}

    def put(self, content: str, tool_call_id: str) -> str:
        self._purge()
        digest = hashlib.sha256(f"{tool_call_id}\0{content}".encode()).hexdigest()[:24]
        self._items[digest] = Artifact(digest, content, tool_call_id, time.monotonic())
        while sum(len(item.content) for item in self._items.values()) > self._max_chars:
            oldest = min(self._items.values(), key=lambda item: item.created_at)
            del self._items[oldest.id]
        return digest

    def get(self, artifact_id: str, *, offset: int = 0, limit: int = 8_000) -> str | None:
        self._purge()
        item = self._items.get(artifact_id)
        if item is None:
            return None
        return item.content[max(0, offset) : max(0, offset) + max(1, limit)]

    def _purge(self) -> None:
        now = time.monotonic()
        self._items = {
            key: item for key, item in self._items.items() if now - item.created_at <= self._ttl
        }
