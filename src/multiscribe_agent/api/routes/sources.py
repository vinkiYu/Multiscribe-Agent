"""Authenticated source-adapter configuration endpoints."""
# ruff: noqa: B008

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import AdapterConfig
from multiscribe_agent.plugins.registry import AdapterRegistry

router = APIRouter(
    prefix="/api/sources", tags=["sources"], dependencies=[Depends(get_current_user)]
)

_MASKED_VALUE = "********"
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "webhook",
)


@router.get("")
async def list_sources(
    context: ServiceContext = Depends(get_context),
) -> dict[str, object]:
    """Return saved source configurations and the discovered adapter form contracts."""
    return {
        "sources": [_source_response(source) for source in context.settings.adapters],
        "available_adapters": [
            metadata.model_dump(mode="json")
            for metadata in AdapterRegistry.get_instance().list_metadata()
        ],
    }


@router.put("/{source_id}")
async def save_source(
    source_id: str,
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),
) -> dict[str, object]:
    """Create or replace one source configuration and persist it as a settings override."""
    if not source_id.strip():
        raise HTTPException(status_code=400, detail="source_id must not be empty")
    if context.config_service is None:
        raise HTTPException(status_code=503, detail="configuration service unavailable")

    existing = next(
        (source for source in context.settings.adapters if source.id == source_id), None
    )
    candidate = dict(payload)
    candidate["id"] = source_id
    raw_config = candidate.get("config")
    if existing is not None and isinstance(raw_config, Mapping):
        candidate["config"] = _merge_masked_config(existing.config, dict(raw_config))

    try:
        source = AdapterConfig.model_validate(candidate)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors()) from exc

    updated_sources = [item for item in context.settings.adapters if item.id != source_id]
    updated_sources.append(source)
    context.settings.adapters = updated_sources

    overrides = await context.config_service.load_overrides()
    overrides["adapters"] = [item.model_dump(mode="json") for item in updated_sources]
    await context.config_service.save_settings(overrides)
    return _source_response(source)


def _source_response(source: AdapterConfig) -> dict[str, object]:
    """Serialize one source without exposing credential-like configuration values."""
    data = source.model_dump(mode="json")
    config = data["config"]
    if not isinstance(config, dict):
        raise RuntimeError("adapter config must be a JSON object")
    data["config"] = _redact_config(config)
    return data


def _merge_masked_config(
    existing: Mapping[str, Any], incoming: Mapping[str, object]
) -> dict[str, object]:
    """Retain an existing sensitive value when a masked read-model value is returned."""
    merged = dict(incoming)
    for key, value in incoming.items():
        if _is_sensitive_key(key) and value == _MASKED_VALUE and key in existing:
            merged[key] = existing[key]
    return merged


def _redact_config(config: Mapping[str, Any]) -> dict[str, object]:
    """Return a shallow safe view of adapter configuration for browser clients."""
    return {
        key: _MASKED_VALUE if _is_sensitive_key(key) and value else value
        for key, value in config.items()
    }


def _is_sensitive_key(key: str) -> bool:
    """Recognize configuration keys that must not leave the server in clear text."""
    normalized = key.lower()
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)
