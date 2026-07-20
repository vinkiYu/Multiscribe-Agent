"""Double-submit cookie CSRF protection for browser-submitted state changes."""

from __future__ import annotations

import secrets
from collections.abc import Iterable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

CSRF_COOKIE_NAME = "multiscribe_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class CsrfMiddleware(BaseHTTPMiddleware):
    """Validate a header token against the non-HttpOnly cookie token."""

    def __init__(self, app: ASGIApp, *, exempt_paths: Iterable[str] = ()) -> None:
        super().__init__(app)
        self._exempt_paths = frozenset(exempt_paths)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await self._handle(request, call_next)
        if not request.cookies.get(CSRF_COOKIE_NAME):
            response.set_cookie(
                CSRF_COOKIE_NAME,
                secrets.token_urlsafe(32),
                httponly=False,
                samesite="lax",
                secure=request.url.scheme == "https",
            )
        return response

    async def _handle(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in SAFE_METHODS or self._is_exempt(request.url.path):
            return await call_next(request)

        # Programmatic API clients authenticate with a bearer token and do not
        # expose the browser cookie; those requests are not CSRF-replayable.
        if request.headers.get("Authorization", "").startswith("Bearer "):
            return await call_next(request)

        if request.method in STATE_CHANGING_METHODS:
            cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
            header_token = request.headers.get(CSRF_HEADER_NAME)
            if (
                not cookie_token
                or not header_token
                or not secrets.compare_digest(cookie_token, header_token)
            ):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token missing or mismatched"},
                )
        return await call_next(request)

    def _is_exempt(self, path: str) -> bool:
        """Match exact or prefix exemptions, including API subroutes."""
        return any(path == exempt or path.startswith(exempt) for exempt in self._exempt_paths)
