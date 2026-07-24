"""Shared fakes and fixtures for LLM provider unit tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from langchain_core.messages import AIMessage as LCAIMessage

from multiscribe_agent.config import ProviderConfig
from multiscribe_agent.domain.models import AIMessage, ToolDefinition


class FakeChatModel:
    """In-memory LangChain chat-model substitute with configurable responses."""

    def __init__(self, **kwargs: object) -> None:
        """Capture constructor arguments without performing I/O."""
        self.kwargs = kwargs
        self.response = LCAIMessage(content="")
        self.chunks: list[LCAIMessage] = []
        self.bound_tools: list[dict[str, object]] | None = None
        self.invocations: list[list[object]] = []
        self.bound_kwargs: dict[str, object] = {}
        self.error: Exception | None = None

    def bind(self, **kwargs: object) -> FakeChatModel:
        """Record per-call model arguments and return this model."""
        self.bound_kwargs.update(kwargs)
        return self

    def bind_tools(self, tools: list[dict[str, object]]) -> FakeChatModel:
        """Record bound tools and return this model like LangChain does."""
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages: list[object]) -> LCAIMessage:
        """Return the configured response without a network call."""
        self.invocations.append(messages)
        if self.error is not None:
            raise self.error
        return self.response

    async def astream(self, messages: list[object]) -> AsyncIterator[LCAIMessage]:
        """Yield configured chunks without a network call."""
        self.invocations.append(messages)
        if self.error is not None:
            raise self.error
        for chunk in self.chunks:
            yield chunk


@pytest.fixture
def openai_config() -> ProviderConfig:
    """Provide a configured OpenAI endpoint suitable for unit tests."""
    return ProviderConfig(
        id="openai-test",
        name="OpenAI test",
        type="openai",
        api_key="test-key",
        models=["gpt-test"],
    )


@pytest.fixture
def anthropic_config() -> ProviderConfig:
    """Provide a configured Anthropic endpoint suitable for unit tests."""
    return ProviderConfig(
        id="anthropic-test",
        name="Anthropic test",
        type="anthropic",
        api_key="test-key",
        models=["claude-test"],
    )


@pytest.fixture
def user_message() -> list[AIMessage]:
    """Provide one simple conversation message."""
    return [AIMessage(role="user", content="hello")]


@pytest.fixture
def weather_tool() -> ToolDefinition:
    """Provide a representative JSON-schema tool definition."""
    return ToolDefinition(
        id="weather",
        name="get_weather",
        description="Get weather by city.",
        parameters={"type": "object", "properties": {"city": {"type": "string"}}},
    )
