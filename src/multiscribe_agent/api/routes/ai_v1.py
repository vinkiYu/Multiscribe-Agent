"""External AI access: registration, tool discovery, and execution gateway."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.services.interop import InteropError, InteropService
from multiscribe_agent.services.interop_rate_limit import RateLimitExceeded, SlidingWindowLimiter
from multiscribe_agent.services.interop_registry import UnknownToolError

router = APIRouter(prefix="/api/ai/v1", tags=["interop"])


def _service(context: ServiceContext) -> InteropService:
    if context.interop_service is None:
        raise HTTPException(status_code=503, detail="interop service unavailable")
    return context.interop_service


def _limiter(context: ServiceContext) -> SlidingWindowLimiter:
    if context.interop_limiter is None:
        raise HTTPException(status_code=503, detail="interop limiter unavailable")
    return context.interop_limiter


@router.post("/register")
async def register(
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Mint a new external AI API key; plaintext is returned once."""
    description = str(payload.get("description", "")).strip()[:200]
    auto_approve = payload.get("auto_approve", True)
    if not isinstance(auto_approve, bool):
        raise HTTPException(status_code=400, detail="auto_approve must be boolean")
    mode: Literal["whitelist", "approval"] = "whitelist" if auto_approve else "approval"
    issued = await _service(context).generate_key(description, mode=mode)
    return {"api_key": issued.api_key, "key_id": issued.key_id, "approved": auto_approve}


@router.put("/keys/{key_id}/approve")
async def approve(
    key_id: str,
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, str]:
    """Approve a key created in manual approval mode."""
    if not await _service(context).approve_key(key_id):
        raise HTTPException(status_code=404, detail="key not found")
    return {"status": "approved"}


@router.get("/tools")
async def tools(context: ServiceContext = Depends(get_context)) -> dict[str, object]:  # noqa: B008
    """Return the OpenAI Function Calling tool list."""
    if context.interop_registry is None:
        raise HTTPException(status_code=503, detail="tool registry unavailable")
    return {"tools": context.interop_registry.list_schemas()}


@router.post("/execute")
async def execute(
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
    x_api_key: str | None = Header(default=None),
) -> dict[str, object]:
    """Authenticate, rate-limit, and dispatch a single external tool call."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="missing X-API-Key")
    try:
        record = await _service(context).verify_key(x_api_key)
    except InteropError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    try:
        _limiter(context).check(record.key_id, record.rate_limit_per_minute)
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    registry = context.interop_registry
    if registry is None:
        raise HTTPException(status_code=503, detail="tool registry unavailable")
    tool_name = payload.get("name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=400, detail="arguments must be an object")
    await _service(context).touch_usage(record.key_id)
    try:
        output = await registry.execute(tool_name.strip(), arguments)
    except UnknownToolError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "tool": tool_name.strip(), "output": output}
