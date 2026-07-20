"""FastAPI application factory with lifecycle, access logging, and error mapping."""

from __future__ import annotations

import mimetypes
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from multiscribe_agent.api.middleware import CsrfMiddleware, EndpointRateLimiter
from multiscribe_agent.api.routes import (
    agents,
    ai_v1,
    auth,
    dashboard,
    digest,
    knowledge,
    mcp,
    memory,
    metrics,
    publish_history,
    schedules,
    skills,
    workflows,
)
from multiscribe_agent.bootstrap import ServiceContext, get_context
from multiscribe_agent.config import SystemSettings
from multiscribe_agent.core.errors import (
    AuthError,
    MultiscribeError,
    ProviderError,
    ValidationError,
)
from multiscribe_agent.core.logging import configure_logging, get_logger


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built React SPA when its production bundle is available."""
    dist_path = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist_path.is_dir():
        # Windows maps .css to application/x-css, which Chromium rejects for stylesheets.
        mimetypes.add_type("text/css", ".css", strict=True)
        # Register last so API and documentation routes keep precedence over the SPA.
        app.mount("/", StaticFiles(directory=dist_path, html=True), name="frontend")


def create_app(settings: SystemSettings, context: ServiceContext | None = None) -> FastAPI:
    """Create the configured HTTP application and attach its service composition root."""
    configure_logging(settings.log_level, json_output=True)
    service_context = context or get_context()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await service_context.init()
        yield
        await service_context.close()

    app = FastAPI(title="MultiscribeAgent", lifespan=lifespan)
    app.state.settings = settings
    app.state.context = service_context
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if settings.csrf_enabled:
        app.add_middleware(CsrfMiddleware, exempt_paths=settings.csrf_exempt_paths)
    if settings.rate_limit.enabled:
        app.add_middleware(
            EndpointRateLimiter,
            rules=settings.rate_limit.rules,
            exempt_paths=settings.rate_limit.exempt_paths,
        )

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        """Return a lightweight process health probe."""
        return {"status": "ok"}

    @app.middleware("http")
    async def access_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        trace_id = uuid4().hex
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        try:
            response = await call_next(request)
            get_logger().info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
            )
            response.headers["X-Trace-Id"] = trace_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()

    @app.exception_handler(MultiscribeError)
    async def domain_error(_: Request, exc: MultiscribeError) -> JSONResponse:
        code = (
            401
            if isinstance(exc, AuthError)
            else 400
            if isinstance(exc, ValidationError)
            else 502
            if isinstance(exc, ProviderError)
            else 500
        )
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    for router in (
        auth.router,
        ai_v1.router,
        metrics.router,
        dashboard.router,
        digest.router,
        knowledge.router,
        memory.router,
        mcp.router,
        publish_history.router,
        skills.router,
        agents.router,
        workflows.router,
        schedules.router,
    ):
        app.include_router(router)
    _mount_frontend(app)
    return app
