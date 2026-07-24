"""Tests for provider normalization helpers and factory selection."""

from __future__ import annotations

import pytest
from langchain_core.messages import (
    AIMessage as LCAIMessage,
)
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from multiscribe_agent.config import ProviderConfig
from multiscribe_agent.core.errors import ProviderContextLengthError, ProviderError
from multiscribe_agent.domain.models import AIMessage, ToolCall, ToolDefinition
from multiscribe_agent.llm.provider import (
    create_provider,
    from_lc_message,
    is_context_length_error,
    merge_tool_call_deltas,
    normalize_provider_error,
    normalize_tools,
    to_lc_bindable_tools,
    to_lc_messages,
)
from multiscribe_agent.llm.providers.anthropic import AnthropicProvider
from multiscribe_agent.llm.providers.openai import OpenAIProvider


def test_to_lc_messages_preserves_roles_and_tool_calls() -> None:
    """Domain roles and tool-call arguments are converted to LangChain messages."""
    messages = [
        AIMessage(role="user", content="question"),
        AIMessage(
            role="assistant",
            content="calling tool",
            tool_calls=[ToolCall(id="call-1", name="weather", arguments={"city": "Beijing"})],
        ),
        AIMessage(role="tool", content="sunny", tool_call_id="call-1", name="weather"),
    ]

    normalized = to_lc_messages(messages, "be concise")

    assert isinstance(normalized[0], SystemMessage)
    assert isinstance(normalized[1], HumanMessage)
    assert isinstance(normalized[2], LCAIMessage)
    assert normalized[2].tool_calls == [
        {"name": "weather", "args": {"city": "Beijing"}, "id": "call-1", "type": "tool_call"}
    ]
    assert isinstance(normalized[3], ToolMessage)
    assert normalized[3].tool_call_id == "call-1"


def test_from_lc_message_preserves_image_tool_calls_and_usage() -> None:
    """Multimodal content, tool calls, and usage metadata normalize to the domain model."""
    message = LCAIMessage(
        content=[
            {"type": "text", "text": "Describe this image"},
            {"type": "image_url", "image_url": {"url": "https://example.test/image.png"}},
        ],
        tool_calls=[
            {
                "name": "describe_image",
                "args": {"detail": "high"},
                "id": "call-2",
                "type": "tool_call",
            }
        ],
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )

    response = from_lc_message(message)

    assert "image_url" in response.content
    assert response.tool_calls == [
        ToolCall(id="call-2", name="describe_image", arguments={"detail": "high"})
    ]
    assert response.usage is not None
    assert response.usage.total_tokens == 15


def test_normalize_tools_uses_langchain_schema_shape() -> None:
    """Tool metadata is converted into the task package's bind-tools shape."""
    tool = ToolDefinition(
        id="weather",
        name="weather",
        description="Get current weather.",
        parameters={"type": "object"},
    )

    assert normalize_tools([tool]) == [
        {"name": "weather", "description": "Get current weather.", "schema": {"type": "object"}}
    ]
    assert to_lc_bindable_tools([tool]) == [
        {
            "name": "weather",
            "description": "Get current weather.",
            "parameters": {"type": "object"},
        }
    ]


def test_merge_tool_call_deltas_concatenates_arguments() -> None:
    """String tool-call fragments become one complete argument string."""
    merged = merge_tool_call_deltas(
        [ToolCall(id="call-3", name="weather", arguments='{"city":"')],
        [ToolCall(id="call-3", name="weather", arguments='Beijing"}')],
    )

    assert merged == [ToolCall(id="call-3", name="weather", arguments='{"city":"Beijing"}')]


def test_create_provider_dispatches_to_openai(openai_config: ProviderConfig) -> None:
    """The factory selects OpenAI and uses the endpoint's first configured model."""
    provider = create_provider(openai_config)

    assert isinstance(provider, OpenAIProvider)


def test_create_provider_dispatches_to_anthropic(anthropic_config: ProviderConfig) -> None:
    """The factory selects Anthropic and accepts a per-agent model override."""
    provider = create_provider(anthropic_config, model="claude-override", temperature=0.2)

    assert isinstance(provider, AnthropicProvider)


def test_create_provider_rejects_missing_model(openai_config: ProviderConfig) -> None:
    """A provider cannot be constructed without an explicit or configured model."""
    openai_config.models = []

    with pytest.raises(ProviderError, match="no model configured for provider openai-test"):
        create_provider(openai_config)


def test_create_provider_rejects_unknown_type() -> None:
    """Unexpected provider types produce the domain-specific configuration error."""
    unknown_config = ProviderConfig.model_construct(
        id="unknown",
        name="Unknown",
        type="unknown",
        api_key="test-key",
        models=["test-model"],
    )

    with pytest.raises(ProviderError, match="unknown provider type"):
        create_provider(unknown_config)


def test_create_provider_marks_optional_providers_as_deferred() -> None:
    """Google and Ollama have an explicit P18 follow-up path rather than silent failure."""
    google_config = ProviderConfig(
        id="google-test",
        name="Google test",
        type="google",
        models=["gemini-test"],
    )

    with pytest.raises(NotImplementedError, match="deferred to P18"):
        create_provider(google_config)


@pytest.mark.parametrize(
    "message",
    [
        "context_length_exceeded",
        "maximum context length is 128000 tokens",
        "prompt is too long",
    ],
)
def test_context_length_errors_are_classified_for_compatible_endpoints(message: str) -> None:
    error = RuntimeError(message)

    assert is_context_length_error(error)
    assert isinstance(normalize_provider_error(error, "Proxy"), ProviderContextLengthError)


def test_unrelated_provider_error_is_not_misclassified() -> None:
    error = RuntimeError("invalid api key")

    assert not is_context_length_error(error)
    assert type(normalize_provider_error(error, "Proxy")) is ProviderError
