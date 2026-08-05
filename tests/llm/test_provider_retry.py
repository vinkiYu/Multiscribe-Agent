"""Regression tests for bounded retries around non-streaming provider calls."""

from __future__ import annotations

import httpx
import pytest
from langchain_core.messages import AIMessage as LCAIMessage

from multiscribe_agent.config import ProviderConfig
from multiscribe_agent.core.errors import ProviderError
from multiscribe_agent.domain.models import AIMessage
from multiscribe_agent.llm.providers.anthropic import AnthropicProvider
from multiscribe_agent.llm.providers.openai import OpenAIProvider


class _SequenceModel:
    """Minimal async chat model that emits a configured sequence of outcomes."""

    def __init__(self, outcomes: list[BaseException | LCAIMessage]) -> None:
        self._outcomes = outcomes
        self.calls = 0

    async def ainvoke(self, _messages: list[object]) -> LCAIMessage:
        self.calls += 1
        outcome = self._outcomes[min(self.calls - 1, len(self._outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def bind_tools(self, _tools: list[dict[str, object]]) -> _SequenceModel:
        return self

    def bind(self, **_kwargs: object) -> _SequenceModel:
        return self


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://provider.example.test/v1/chat/completions")
    return httpx.HTTPStatusError(
        f"HTTP {status}", request=request, response=httpx.Response(status, request=request)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_type", "provider_class", "client_path"),
    [
        ("openai", OpenAIProvider, "multiscribe_agent.llm.providers.openai.ChatOpenAI"),
        ("anthropic", AnthropicProvider, "multiscribe_agent.llm.providers.anthropic.ChatAnthropic"),
    ],
)
async def test_generate_retries_transient_errors_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    provider_type: str,
    provider_class: type[OpenAIProvider] | type[AnthropicProvider],
    client_path: str,
) -> None:
    """Both concrete providers retry 429/5xx failures without changing stream."""
    model = _SequenceModel([_http_error(429), _http_error(503), LCAIMessage(content="ok")])
    monkeypatch.setattr(client_path, lambda **_: model)
    monkeypatch.setattr("multiscribe_agent.llm.provider.asyncio.sleep", _no_sleep)
    config = ProviderConfig(
        id=f"{provider_type}-retry",
        name="retry test",
        type=provider_type,
        api_key="test-key",
        models=["test-model"],
    )

    provider = provider_class(config, "test-model", 0.0)
    response = await provider.generate([AIMessage(role="user", content="hello")])

    assert response.content == "ok"
    assert model.calls == 3


@pytest.mark.asyncio
async def test_generate_does_not_retry_bad_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """A permanent HTTP 400 is surfaced immediately instead of being retried."""
    model = _SequenceModel([_http_error(400)])
    monkeypatch.setattr("multiscribe_agent.llm.providers.openai.ChatOpenAI", lambda **_: model)
    monkeypatch.setattr("multiscribe_agent.llm.provider.asyncio.sleep", _no_sleep)
    config = ProviderConfig(
        id="openai-bad-request",
        name="bad request test",
        type="openai",
        api_key="test-key",
        models=["test-model"],
    )

    with pytest.raises(ProviderError):
        await OpenAIProvider(config, "test-model", 0.0).generate(
            [AIMessage(role="user", content="hello")]
        )

    assert model.calls == 1


@pytest.mark.asyncio
async def test_generate_exhaustion_preserves_provider_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exhaustion returns ProviderError while retaining the final HTTP cause."""
    model = _SequenceModel([_http_error(500)] * 4)
    monkeypatch.setattr("multiscribe_agent.llm.providers.openai.ChatOpenAI", lambda **_: model)
    monkeypatch.setattr("multiscribe_agent.llm.provider.asyncio.sleep", _no_sleep)
    config = ProviderConfig(
        id="openai-exhausted",
        name="exhausted test",
        type="openai",
        api_key="test-key",
        models=["test-model"],
    )

    with pytest.raises(ProviderError) as caught:
        await OpenAIProvider(config, "test-model", 0.0).generate(
            [AIMessage(role="user", content="hello")]
        )

    assert model.calls == 4
    assert isinstance(caught.value.__cause__, ProviderError)
    assert isinstance(caught.value.__cause__.__cause__, httpx.HTTPStatusError)


async def _no_sleep(_seconds: float) -> None:
    """Skip real backoff delays in unit tests."""
