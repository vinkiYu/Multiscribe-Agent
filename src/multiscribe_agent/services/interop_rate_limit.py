"""In-memory sliding-window rate limiter for interop API keys."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field


class RateLimitExceeded(RuntimeError):
    """Raised when a key exceeds its configured request quota."""


@dataclass(slots=True)
class SlidingWindowLimiter:
    """Track request timestamps per key in bounded deques."""

    window_seconds: int = 60
    _hits: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def check(self, key_id: str, limit: int) -> None:
        """Drop expired hits, then record a request or raise on quota exhaustion."""
        if limit <= 0:
            raise ValueError("rate limit must be positive")
        now = time.monotonic()
        cutoff = now - self.window_seconds
        hits = self._hits[key_id]
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= limit:
            raise RateLimitExceeded(f"key {key_id} exceeded {limit} req/{self.window_seconds}s")
        hits.append(now)

    def reset(self) -> None:
        """Clear all windows, primarily for lifecycle reloads and tests."""
        self._hits.clear()
