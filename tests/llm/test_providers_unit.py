"""Mock-only behavior tests for the concrete OpenAI and Anthropic providers."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from conftest import FakeChatModel
from langchain_core.messages import AIMessage as LCAIMessage
from langchain_core.messages import AIMessageChunk

from multiscribe_agent.config import ProviderConfig
from multiscribe_agent.core.errors import ProviderContextLengthError, ProviderError
from multiscribe_agent.domain.models import AIMessage, ToolCall, ToolDefinition
from multiscribe_agent.llm.providers.anthropic import AnthropicProvider
from multiscribe_agent.llm.providers.openai import OpenAIProvider


async def _collect(responses: AsyncIterator[object]) -> list[object]:
    """Materialize an async provider stream for assertions."""
    return [response async for response in responses]


@pytest.mark.asyncio
async def test_openai_generate_uses_mock_model_and_normalizes_tools(
    monkeypatch: pytest.MonkeyPatch,
    openai_config: ProviderConfig,
    user_message: list[AIMessage],
    weather_tool: ToolDefinition,
) -> None:
    """OpenAI generation is fully mockable and returns a normalized tool call."""
    fake_model = FakeChatModel()
    fake_model.response = LCAIMessage(
        content="I will check.",
        tool_calls=[
            {
                "name": "get_weather",
                "args": {"city": "Beijing"},
                "id": "call-1",
                "type": "tool_call",
            }
        ],
    )
    monkeypatch.setattr("multiscribe_agent.llm.providers.openai.ChatOpenAI", lambda **_: fake_model)
    provider = OpenAIProvider(openai_config, "gpt-test", 0.7)

    response = await provider.generate(
        user_message, [weather_tool], "be brief", max_output_tokens=321
    )

    assert response.content == "I will check."
    assert response.tool_calls == [
        ToolCall(id="call-1", name="get_weather", arguments={"city": "Beijing"})
    ]
    assert fake_model.bound_tools is not None
    assert fake_model.bound_tools[0]["parameters"] == weather_tool.parameters
    assert fake_model.bound_kwargs["max_tokens"] == 321


@pytest.mark.asyncio
async def test_openai_stream_merges_tool_call_argument_chunks(
    monkeypatch: pytest.MonkeyPatch,
    openai_config: ProviderConfig,
    user_message: list[AIMessage],
) -> None:
    """OpenAI stream chunks concatenate fragmented tool arguments by call id."""
    fake_model = FakeChatModel()
    fake_model.chunks = [
        AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name": "get_weather", "args": '{"city":"', "id": "call-1", "index": 0}
            ],
        ),
        AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name": "get_weather", "args": 'Beijing"}', "id": "call-1", "index": 0}
            ],
        ),
    ]
    monkeypatch.setattr("multiscribe_agent.llm.providers.openai.ChatOpenAI", lambda **_: fake_model)
    provider = OpenAIProvider(openai_config, "gpt-test", 0.7)

    responses = await _collect(provider.stream(user_message))

    assert len(responses) == 2
    final_response = responses[-1]
    assert hasattr(final_response, "tool_calls")
    assert final_response.tool_calls == [
        ToolCall(id="call-1", name="get_weather", arguments='{"city":"Beijing"}')
    ]


@pytest.mark.asyncio
async def test_anthropic_generate_uses_mock_model(
    monkeypatch: pytest.MonkeyPatch,
    anthropic_config: ProviderConfig,
    user_message: list[AIMessage],
) -> None:
    """Anthropic generation is fully mockable and never makes a real request."""
    fake_model = FakeChatModel()
    fake_model.response = LCAIMessage(content="Anthropic response")
    monkeypatch.setattr(
        "multiscribe_agent.llm.providers.anthropic.ChatAnthropic", lambda **_: fake_model
    )
    provider = AnthropicProvider(anthropic_config, "claude-test", 0.7)

    response = await provider.generate(
        user_message, system_instruction="system prompt", max_output_tokens=654
    )

    assert response.content == "Anthropic response"
    assert fake_model.invocations
    assert fake_model.bound_kwargs["max_tokens"] == 654


@pytest.mark.asyncio
async def test_anthropic_stream_uses_mock_model(
    monkeypatch: pytest.MonkeyPatch,
    anthropic_config: ProviderConfig,
    user_message: list[AIMessage],
) -> None:
    """Anthropic streaming yields locally supplied chunks without real network access."""
    fake_model = FakeChatModel()
    fake_model.chunks = [AIMessageChunk(content="first"), AIMessageChunk(content="second")]
    monkeypatch.setattr(
        "multiscribe_agent.llm.providers.anthropic.ChatAnthropic", lambda **_: fake_model
    )
    provider = AnthropicProvider(anthropic_config, "claude-test", 0.7)

    responses = await _collect(provider.stream(user_message))

    assert [response.content for response in responses] == ["first", "second"]


@pytest.mark.parametrize("provider_class", [OpenAIProvider, AnthropicProvider])
def test_provider_requires_api_key(
    provider_class: type[OpenAIProvider] | type[AnthropicProvider],
) -> None:
    """Configured provider construction fails clearly before any request without a key."""
    config = ProviderConfig(
        id="missing-key",
        name="Missing key",
        type="openai",
        models=["test-model"],
    )

    with pytest.raises(ProviderError, match="no api key configured"):
        provider_class(config, "test-model", 0.7)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name", ["openai", "anthropic"])
async def test_provider_context_error_is_normalized_for_native_and_proxy_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    provider_name: str,
) -> None:
    fake_model = FakeChatModel()
    request = httpx.Request("POST", "https://proxy.example.test/v1/chat/completions")
    response = httpx.Response(400, request=request)
    fake_model.error = httpx.HTTPStatusError(
        "context_length_exceeded", request=request, response=response
    )
    config = ProviderConfig(
        id="proxy",
        name="Proxy",
        type=provider_name,
        api_key="test-key",
        base_url="https://proxy.example.test/v1",
        models=["proxy-model"],
    )
    if provider_name == "openai":
        monkeypatch.setattr(
            "multiscribe_agent.llm.providers.openai.ChatOpenAI", lambda **_: fake_model
        )
        provider = OpenAIProvider(config, "proxy-model", 0.2)
    else:
        monkeypatch.setattr(
            "multiscribe_agent.llm.providers.anthropic.ChatAnthropic", lambda **_: fake_model
        )
        provider = AnthropicProvider(config, "proxy-model", 0.2)

    with pytest.raises(ProviderContextLengthError):
        await provider.generate([AIMessage(role="user", content="too long")])
