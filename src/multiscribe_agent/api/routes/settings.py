"""Authenticated runtime settings endpoints for the console."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings

router = APIRouter(
    prefix="/api/settings", tags=["settings"], dependencies=[Depends(get_current_user)]
)
MASK = "********"
SENSITIVE = ("key", "secret", "token", "password", "webhook", "authorization", "cookie")
SYNC_TIMEOUT_SECONDS = 12.0


@router.get("")
async def get_settings(context: ServiceContext = Depends(get_context)) -> dict[str, object]:  # noqa: B008
    settings = context.settings
    return {
        "ai_providers": [
            _provider_view(provider.model_dump(mode="json")) for provider in settings.ai_providers
        ],
        "publishers": [
            _publisher_view(publisher.model_dump(mode="json")) for publisher in settings.publishers
        ],
        "http_proxy": settings.http_proxy,
        "optional_dependencies": _optional_dependencies(context),
    }


@router.put("")
async def save_settings(
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    if context.config_service is None:
        raise HTTPException(status_code=503, detail="configuration service unavailable")
    allowed = {
        "ai_providers",
        "publishers",
        "http_proxy",
        "provider_context_windows",
        "provider_output_tokens",
    }
    overrides = {key: value for key, value in payload.items() if key in allowed}
    current = context.settings.model_dump(mode="python")
    previous = await context.config_service.load_overrides()
    if isinstance(overrides.get("ai_providers"), list):
        overrides["ai_providers"] = _merge_secret_lists(
            current["ai_providers"], overrides["ai_providers"]
        )
    if isinstance(overrides.get("publishers"), list):
        overrides["publishers"] = _merge_secret_lists(
            current["publishers"], overrides["publishers"]
        )
    merged = {**current, **previous, **overrides}
    try:
        validated = SystemSettings.model_validate(merged)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors()) from exc
    await context.config_service.save_settings(overrides)
    context.settings = validated
    return await get_settings(context)


@router.post("/providers/{provider_id}/models")
async def sync_provider_models(
    provider_id: str,
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Fetch a provider's available model identifiers without persisting a selection."""
    provider = next(
        (item for item in context.settings.ai_providers if item.id == provider_id), None
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    base_url = payload.get("base_url")
    api_key = payload.get("api_key")
    if not isinstance(base_url, str):
        base_url = provider.base_url
    if not isinstance(api_key, str) or api_key == MASK:
        api_key = provider.api_key
    try:
        models, source, note = await _discover_provider_models(provider.type, base_url, api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"provider model list request failed with status {exc.response.status_code}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="provider model list request failed") from exc
    return {"provider_id": provider_id, "models": models, "source": source, "note": note}


@router.post("/providers/{provider_id}/test")
async def check_provider_connection(
    provider_id: str,
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Verify credentials and endpoint access without running an Agent request."""
    provider = next(
        (item for item in context.settings.ai_providers if item.id == provider_id), None
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    base_url = payload.get("base_url")
    api_key = payload.get("api_key")
    if not isinstance(base_url, str):
        base_url = provider.base_url
    if not isinstance(api_key, str) or api_key == MASK:
        api_key = provider.api_key
    try:
        models, _, _ = await _discover_provider_models(provider.type, base_url, api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"provider connection test failed with status {exc.response.status_code}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="provider connection test failed") from exc
    return {"provider_id": provider_id, "ok": True, "model_count": len(models)}


async def _discover_provider_models(
    provider_type: str, base_url: str, api_key: str
) -> tuple[list[str], str, str | None]:
    if provider_type == "anthropic":
        if not api_key:
            raise ValueError("请先填写 Anthropic API 密钥")
        payload = await _get_provider_json(
            f"{(base_url or 'https://api.anthropic.com/v1').rstrip('/')}/models",
            api_key,
            headers={"anthropic-version": "2023-06-01", "x-api-key": api_key},
        )
        return _openai_models(payload), "remote", None
    if provider_type == "openai":
        payload = await _get_provider_json(
            f"{(base_url or 'https://api.openai.com/v1').rstrip('/')}/models", api_key
        )
        return _openai_models(payload), "remote", None
    if provider_type == "google":
        if not api_key:
            raise ValueError("请先填写 Gemini API 密钥")
        payload = await _get_provider_json(
            f"{(base_url or 'https://generativelanguage.googleapis.com/v1beta').rstrip('/')}/models",
            api_key,
            api_key_as_query=True,
        )
        return _google_models(payload), "remote", None
    if provider_type == "ollama":
        payload = await _get_provider_json(
            f"{(base_url or 'http://localhost:11434').rstrip('/')}/api/tags", api_key
        )
        return _ollama_models(payload), "remote", None
    raise ValueError("unsupported provider type")


async def _get_provider_json(
    url: str,
    api_key: str,
    *,
    api_key_as_query: bool = False,
    headers: dict[str, str] | None = None,
) -> object:
    request_headers = (
        {"Authorization": f"Bearer {api_key}"} if api_key and not api_key_as_query else {}
    )
    request_headers.update(headers or {})
    params = {"key": api_key} if api_key and api_key_as_query else None
    async with httpx.AsyncClient(timeout=SYNC_TIMEOUT_SECONDS, follow_redirects=False) as client:
        response = await client.get(url, headers=request_headers, params=params)
    response.raise_for_status()
    return response.json()


def _openai_models(payload: object) -> list[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("provider returned an invalid OpenAI-compatible model list")
    return _model_names(payload["data"], "id")


def _google_models(payload: object) -> list[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise ValueError("provider returned an invalid Gemini model list")
    return [name.removeprefix("models/") for name in _model_names(payload["models"], "name")]


def _ollama_models(payload: object) -> list[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise ValueError("provider returned an invalid Ollama model list")
    return _model_names(payload["models"], "name")


def _model_names(items: list[object], key: str) -> list[str]:
    names: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get(key)
        if isinstance(name, str):
            names.add(name)
    return sorted(names)


def _merge_secret_lists(current: object, incoming: object) -> object:
    if not isinstance(current, list) or not isinstance(incoming, list):
        return incoming
    old = {item.get("id"): item for item in current if isinstance(item, dict)}
    result: list[object] = []
    for item in incoming:
        if not isinstance(item, dict):
            result.append(item)
            continue
        merged = dict(item)
        previous = old.get(item.get("id"), {})
        for key, value in item.items():
            if _is_sensitive(key) and value == MASK and key in previous:
                merged[key] = previous[key]
        if isinstance(item.get("config"), dict) and isinstance(previous.get("config"), dict):
            config = dict(item["config"])
            for key, value in config.items():
                if _is_sensitive(key) and value == MASK and key in previous["config"]:
                    config[key] = previous["config"][key]
            merged["config"] = config
        result.append(merged)
    return result


def _provider_view(data: dict[str, Any]) -> dict[str, Any]:
    data["api_key"] = MASK if data.get("api_key") else ""
    return data


def _publisher_view(data: dict[str, Any]) -> dict[str, Any]:
    if isinstance(data.get("config"), dict):
        data["config"] = {
            key: MASK if _is_sensitive(key) and value else value
            for key, value in data["config"].items()
        }
    return data


def _is_sensitive(key: str) -> bool:
    normalized = key.lower()
    return any(part in normalized for part in SENSITIVE)


def _optional_dependencies(context: ServiceContext) -> dict[str, bool]:
    capabilities = context.observability_capabilities
    return {
        "opentelemetry": bool(capabilities and capabilities.tracer),
        "prometheus": bool(capabilities and capabilities.prometheus_endpoint),
        "vector_search": bool(context.kb_capabilities and context.kb_capabilities.vector_enabled),
    }
