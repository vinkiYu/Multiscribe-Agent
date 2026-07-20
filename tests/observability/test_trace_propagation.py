"""Regression tests for outbound trace header propagation."""

from dataclasses import dataclass

import httpx
import pytest

from multiscribe_agent.observability import trace_headers


@dataclass(frozen=True)
class FakeSpanContext:
    """Minimal OpenTelemetry span context used by the header tests."""

    is_valid: bool
    trace_id: int = 0


class FakeSpan:
    """Return a deterministic span context."""

    def __init__(self, context: FakeSpanContext) -> None:
        self._context = context

    def get_span_context(self) -> FakeSpanContext:
        return self._context


class FakeTraceModule:
    """Module-shaped fake for the optional OTel import."""

    def __init__(self, span: FakeSpan) -> None:
        self._span = span

    def get_current_span(self) -> FakeSpan:
        return self._span


def test_inject_trace_headers_formats_a_valid_trace_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid active span becomes a 32-character hexadecimal header."""
    module = FakeTraceModule(FakeSpan(FakeSpanContext(is_valid=True, trace_id=0x1234)))
    monkeypatch.setattr(trace_headers, "import_module", lambda _: module)

    headers = trace_headers.inject_trace_headers({})

    assert headers["X-Trace-Id"] == "0" * 28 + "1234"


def test_invalid_span_leaves_headers_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """No-op or invalid spans must not create a misleading trace header."""
    module = FakeTraceModule(FakeSpan(FakeSpanContext(is_valid=False)))
    monkeypatch.setattr(trace_headers, "import_module", lambda _: module)
    headers = {"Existing": "value"}

    assert trace_headers.inject_trace_headers(headers) == headers
    assert "X-Trace-Id" not in headers


@pytest.mark.asyncio
async def test_httpx_request_hook_injects_trace_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """The request-level hook reads the active span at send time."""
    module = FakeTraceModule(FakeSpan(FakeSpanContext(is_valid=True, trace_id=0xABCD)))
    monkeypatch.setattr(trace_headers, "import_module", lambda _: module)
    seen: list[str | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("X-Trace-Id"))
        return httpx.Response(200)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        event_hooks={"request": [trace_headers.trace_request_hook]},
    ) as client:
        response = await client.get("https://example.test/trace")

    assert response.status_code == 200
    assert seen == ["0" * 28 + "abcd"]


def test_extract_trace_id_is_case_insensitive() -> None:
    """Inbound headers can be represented with any HTTP header casing."""
    assert trace_headers.extract_trace_id_from_headers({"x-trace-id": " abc "}) == "abc"
