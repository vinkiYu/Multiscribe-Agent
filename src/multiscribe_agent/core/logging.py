"""Structured logging configuration with recursive secret redaction."""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from importlib import import_module
from typing import Any, cast

import structlog

SENSITIVE_KEY_PARTS = ("token", "secret", "password", "key", "cookie", "auth", "webhook")


def configure_logging(log_level: str, *, json_output: bool = True) -> None:
    """Configure structlog for JSON production output or readable development output."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO), format="%(message)s"
    )
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            _inject_trace_id,
            structlog.contextvars.merge_contextvars,
            _redact_sensitive,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def _inject_trace_id(
    _logger: object, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Add the current OTel trace id when the optional SDK is active."""
    try:
        trace = import_module("opentelemetry.trace")
    except ImportError:
        return event_dict
    span = trace.get_current_span()
    context = span.get_span_context()
    if context.is_valid:
        event_dict.setdefault("trace_id", format(context.trace_id, "032x"))
    return event_dict


def get_logger() -> structlog.stdlib.BoundLogger:
    """Return the configured structured application logger."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger())


def _redact_sensitive(
    _: object, __: str, event_dict: MutableMapping[str, object]
) -> MutableMapping[str, object]:
    """Mask values whose keys indicate secrets, recursively across nested mappings."""
    return cast(MutableMapping[str, object], _redact_mapping(event_dict))


def _redact_mapping(values: MutableMapping[str, object]) -> dict[str, object]:
    """Return a recursively redacted copy without mutating caller-owned event data."""
    redacted: dict[str, object] = {}
    for key, value in values.items():
        if any(part in key.casefold() for part in SENSITIVE_KEY_PARTS):
            redacted[key] = _mask(value)
        elif isinstance(value, MutableMapping):
            redacted[key] = _redact_mapping(value)
        elif isinstance(value, list):
            redacted[key] = [
                _redact_mapping(item) if isinstance(item, MutableMapping) else item
                for item in value
            ]
        else:
            redacted[key] = value
    return redacted


def _mask(value: object) -> str:
    """Keep a short non-sensitive shape while never returning the original value."""
    text = str(value)
    return "****" if len(text) <= 8 else f"{text[:4]}****{text[-4:]}"
