"""Tool validation, approval, and sensitive-data protection."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from multiscribe_agent.core.errors import ToolExecutionError
from multiscribe_agent.domain.models import ToolCall

SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "webhook",
)
REDACTED = "[REDACTED]"
_BEARER_PATTERN = re.compile(r"(?i)\b(bearer\s+)[a-z0-9._~+/=-]{8,}")
_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|password|secret|token|webhook)\b(\s*[:=]\s*)([^\s,;]+)"
)


def redact_text(value: str) -> str:
    """Remove common credentials from text before it enters logs or model context."""
    value = _BEARER_PATTERN.sub(r"\1" + REDACTED, value)
    return _ASSIGNMENT_PATTERN.sub(r"\1\2" + REDACTED, value)


def redact_data(value: object, *, key: str | None = None) -> object:
    """Recursively redact values under credential-like keys."""
    if key is not None and any(part in key.casefold() for part in SENSITIVE_KEY_PARTS):
        return REDACTED
    if isinstance(value, Mapping):
        return {
            str(item_key): redact_data(item, key=str(item_key)) for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, tuple):
        return [redact_data(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def normalize_arguments(arguments: dict[str, Any] | str) -> dict[str, Any]:
    """Decode a tool argument object and reject every other JSON shape."""
    if isinstance(arguments, str):
        try:
            decoded = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ToolExecutionError("tool arguments must be valid JSON") from exc
        if not isinstance(decoded, dict):
            raise ToolExecutionError("tool arguments must decode to an object")
        return decoded
    return dict(arguments)


def validate_arguments(arguments: Mapping[str, Any], schema: Mapping[str, object]) -> None:
    """Validate the JSON-Schema subset used by built-in tool declarations."""
    if schema.get("type") == "object" and not isinstance(arguments, Mapping):
        raise ToolExecutionError("tool arguments must be an object")
    required = schema.get("required", [])
    if isinstance(required, list):
        missing = [name for name in required if isinstance(name, str) and name not in arguments]
        if missing:
            raise ToolExecutionError(f"missing required tool argument: {missing[0]}")
    properties = schema.get("properties", {})
    typed_properties = properties if isinstance(properties, Mapping) else {}
    if schema.get("additionalProperties") is False:
        unknown = sorted(set(arguments) - set(typed_properties))
        if unknown:
            raise ToolExecutionError(f"unexpected tool argument: {unknown[0]}")
    for name, value in arguments.items():
        raw_rule = typed_properties.get(name)
        if isinstance(raw_rule, Mapping):
            _validate_value(name, value, raw_rule)


def _validate_value(name: str, value: object, rule: Mapping[str, object]) -> None:
    expected = rule.get("type")
    valid = {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, int | float) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "object": isinstance(value, Mapping),
        "array": isinstance(value, list),
    }
    if isinstance(expected, str) and expected in valid and not valid[expected]:
        raise ToolExecutionError(f"tool argument '{name}' must be {expected}")
    enum = rule.get("enum")
    if isinstance(enum, list) and value not in enum:
        raise ToolExecutionError(f"tool argument '{name}' is not an allowed value")
    if isinstance(value, int | float) and not isinstance(value, bool):
        minimum = rule.get("minimum")
        maximum = rule.get("maximum")
        if isinstance(minimum, int | float) and value < minimum:
            raise ToolExecutionError(f"tool argument '{name}' is below minimum")
        if isinstance(maximum, int | float) and value > maximum:
            raise ToolExecutionError(f"tool argument '{name}' is above maximum")
    if isinstance(value, list):
        item_rule = rule.get("items")
        if isinstance(item_rule, Mapping):
            for index, item in enumerate(value):
                _validate_value(f"{name}[{index}]", item, item_rule)


def tool_call_fingerprint(tool_call: ToolCall) -> str:
    """Bind approval to the exact tool name and canonical arguments."""
    arguments = normalize_arguments(tool_call.arguments)
    payload = json.dumps(
        {"name": tool_call.name, "arguments": arguments},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ApprovalGrant:
    """One short-lived approval bound to a tool call fingerprint."""

    token_hash: str
    fingerprint: str
    expires_at: float


class ToolApprovalStore:
    """Issue and consume one-time approvals outside model-controlled arguments."""

    def __init__(self) -> None:
        self._grants: dict[str, ApprovalGrant] = {}

    def approve(self, tool_call: ToolCall, *, ttl_seconds: float = 300) -> str:
        """Return an opaque operator grant for one exact call."""
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        token = secrets.token_urlsafe(32)
        token_hash = self._token_hash(token)
        self._grants[token_hash] = ApprovalGrant(
            token_hash=token_hash,
            fingerprint=tool_call_fingerprint(tool_call),
            expires_at=time.monotonic() + ttl_seconds,
        )
        return token

    def consume(self, tool_call: ToolCall, token: str | None) -> bool:
        """Consume a matching unexpired token exactly once."""
        if not token:
            return False
        token_hash = self._token_hash(token)
        grant = self._grants.get(token_hash)
        if grant is None:
            return False
        if grant.expires_at < time.monotonic():
            self._grants.pop(token_hash, None)
            return False
        if not hmac.compare_digest(grant.fingerprint, tool_call_fingerprint(tool_call)):
            return False
        self._grants.pop(token_hash, None)
        return True

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
