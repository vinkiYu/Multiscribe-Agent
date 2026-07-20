"""Inject the active OpenTelemetry trace ID into outbound HTTP requests."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping
from contextlib import suppress
from importlib import import_module
from typing import Protocol

import httpx

TRACE_HEADER = "X-Trace-Id"


class _Request(Protocol):
    """Minimal request surface needed by an httpx event hook."""

    headers: MutableMapping[str, str]


def inject_trace_headers(headers: MutableMapping[str, str]) -> MutableMapping[str, str]:
    """Add the current span's trace ID, leaving headers unchanged without a valid span."""
    try:
        trace = import_module("opentelemetry.trace")
    except ImportError:
        return headers

    span = trace.get_current_span()
    context = span.get_span_context()
    if not context.is_valid:
        return headers
    headers[TRACE_HEADER] = format(context.trace_id, "032x")
    return headers


def extract_trace_id_from_headers(headers: Mapping[str, str] | None) -> str | None:
    """Read an inbound trace ID using case-insensitive header lookup."""
    if headers is None:
        return None
    for key, value in headers.items():
        if key.lower() == TRACE_HEADER.lower() and value.strip():
            return value.strip()
    return None


async def trace_request_hook(request: _Request) -> None:
    """Inject the active trace ID immediately before an httpx request is sent."""
    inject_trace_headers(request.headers)


class _DynamicTraceHeaders(Mapping[str, str]):
    """Mapping evaluated by provider SDKs when they build each request."""

    def _snapshot(self) -> dict[str, str]:
        return dict(inject_trace_headers({}))

    def __getitem__(self, key: str) -> str:
        return self._snapshot()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._snapshot())

    def __len__(self) -> int:
        return len(self._snapshot())


def install_trace_propagation(provider: object) -> int:
    """Attach request hooks to provider-owned httpx clients and dynamic SDK headers.

    Provider implementations are intentionally kept behind the provider-neutral factory.
    This installer follows their stable client attributes without importing concrete provider
    classes, so trace propagation remains optional and degrades when a client is unavailable.

    Returns:
        Number of httpx clients that received the request hook.
    """
    installed = 0
    visited: set[int] = set()
    pending: list[tuple[object, int]] = [(provider, 0)]
    while pending:
        current, depth = pending.pop()
        identity = id(current)
        if identity in visited:
            continue
        visited.add(identity)

        if isinstance(current, httpx.AsyncClient):
            installed += _install_client_hook(current)
            continue
        if depth >= 3:
            continue

        if hasattr(current, "default_headers"):
            with suppress(AttributeError, TypeError, ValueError):
                vars(current)["default_headers"] = _DynamicTraceHeaders()

        for attribute in (
            "_http_client",
            "http_async_client",
            "root_async_client",
            "root_client",
            "_client",
        ):
            try:
                nested = getattr(current, attribute, None)
            except (AttributeError, OSError):
                nested = None
            if nested is not None:
                pending.append((nested, depth + 1))
    return installed


def _install_client_hook(client: httpx.AsyncClient) -> int:
    """Install the request hook once on one httpx async client."""
    hooks = client._event_hooks.get("request", [])
    if trace_request_hook not in hooks:
        hooks.append(trace_request_hook)
        return 1
    return 0
