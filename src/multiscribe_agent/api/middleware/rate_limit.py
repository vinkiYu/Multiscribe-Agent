"""Per-path sliding-window rate limiting for human-facing API endpoints."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from time import monotonic

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


class EndpointRateLimiter(BaseHTTPMiddleware):
    """Limit configured endpoint families independently for each client IP."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        rules: dict[str, tuple[int, int]],
        exempt_paths: Iterable[str] = (),
    ) -> None:
        super().__init__(app)
        self._rules = tuple(
            sorted(
                (
                    (prefix, limit, window_seconds)
                    for prefix, (limit, window_seconds) in rules.items()
                ),
                key=lambda item: len(item[0]),
                reverse=True,
            )
        )
        self._exempt_paths = frozenset(exempt_paths)
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Reject requests that exceed their configured sliding-window quota."""
        path = request.url.path
        if request.method == "OPTIONS" or self._is_exempt(path):
            return await call_next(request)

        matched = self._match_rule(path)
        if matched is None:
            return await call_next(request)

        rule_path, limit, window_seconds = matched
        client_ip = request.client.host if request.client is not None else "unknown"
        key = f"{client_ip}:{rule_path}"
        now = monotonic()
        hits = self._hits[key]
        cutoff = now - window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= limit:
            retry_after = max(1, int(window_seconds - (now - hits[0])) + 1)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"rate limit exceeded: {limit}/{window_seconds}s",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)
        return await call_next(request)

    def _is_exempt(self, path: str) -> bool:
        """Return whether a path is explicitly excluded from rate limiting."""
        return any(path == exempt or path.startswith(exempt) for exempt in self._exempt_paths)

    def _match_rule(self, path: str) -> tuple[str, int, int] | None:
        """Match canonical config paths, including the existing API route aliases."""
        for prefix, limit, window_seconds in self._rules:
            if self._matches(prefix, path):
                return prefix, limit, window_seconds
        return None

    @staticmethod
    def _matches(prefix: str, path: str) -> bool:
        if prefix == "/api/agents/run":
            return path.startswith("/api/agents/") and path.endswith("/run")
        if prefix == "/api/auth/login":
            return path in {"/api/auth/login", "/api/login"}
        return path == prefix or path.startswith(prefix + "/")
