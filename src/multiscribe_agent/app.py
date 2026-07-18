"""FastAPI application factory with lifecycle, access logging, and error mapping."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from multiscribe_agent.api.routes import (
    agents,
    auth,
    dashboard,
    digest,
    publish_history,
    schedules,
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
        dashboard.router,
        digest.router,
        publish_history.router,
        agents.router,
        workflows.router,
        schedules.router,
    ):
        app.include_router(router)
    return app
