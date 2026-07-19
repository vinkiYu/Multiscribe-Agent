"""JWT-protected REST mirror for registered MCP tools."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.mcp.registry import MCPToolRegistry
from multiscribe_agent.mcp.server import build_tool_registry

router = APIRouter(prefix="/api/mcp", tags=["mcp"], dependencies=[Depends(get_current_user)])


@router.get("/tools")
async def list_tools(
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> list[dict[str, object]]:
    """Return MCP-discoverable tool descriptions for authenticated HTTP clients."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "input_schema": spec.input_schema.model_json_schema(),
        }
        for spec in _registry(context).list_tools()
    ]


@router.post("/tools/{tool_name}/call")
async def call_tool(
    tool_name: str,
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Invoke a registered tool with schema validation through the REST mirror."""
    try:
        spec = _registry(context).get(tool_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="MCP tool not found") from exc
    try:
        validated = cast(
            dict[str, object], spec.input_schema.model_validate(payload).model_dump(mode="json")
        )
        return await spec.handler(validated)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors()) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _registry(context: ServiceContext) -> MCPToolRegistry:
    """Build a fresh context-bound tool registry for one HTTP request."""
    return build_tool_registry(context, context.settings)
