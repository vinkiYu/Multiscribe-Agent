"""FastAPI dependencies for accessing the application service context."""

from __future__ import annotations

from typing import cast

from fastapi import Request

from multiscribe_agent.bootstrap import ServiceContext


def get_context(request: Request) -> ServiceContext:
    """Return the initialized ServiceContext attached by the application factory."""
    return cast(ServiceContext, request.app.state.context)
