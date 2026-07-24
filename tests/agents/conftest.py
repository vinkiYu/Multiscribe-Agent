"""Shared fake providers and tools for Agent Harness tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from multiscribe_agent.domain.models import (
    AgentDefinition,
    AIMessage,
    AIResponse,
    ToolCall,
    ToolDefinition,
)


class FakeProvider:
    """Deterministic provider with separate streamed rounds and generated responses."""

    def __init__(
        self,
        streamed_rounds: list[list[AIResponse]] | None = None,
        generated_responses: list[AIResponse] | None = None,
    ) -> None:
        """Configure responses returned without external I/O."""
        self.streamed_rounds = list(streamed_rounds or [])
        self.generated_responses = list(generated_responses or [])
        self.stream_inputs: list[list[AIMessage]] = []
        self.generate_inputs: list[list[AIMessage]] = []
        self.generate_output_limits: list[int | None] = []

    async def generate(
        self,
        messages: list[AIMessage],
        tools: list[ToolDefinition] | None = None,
        system_instruction: str | None = None,
        max_output_tokens: int | None = None,
    ) -> AIResponse:
        """Return the next configured non-streaming response."""
        del tools, system_instruction
        self.generate_inputs.append(messages)
        self.generate_output_limits.append(max_output_tokens)
        if not self.generated_responses:
            raise AssertionError("no fake generated response configured")
        return self.generated_responses.pop(0)

    async def stream(
        self,
        messages: list[AIMessage],
        tools: list[ToolDefinition] | None = None,
        system_instruction: str | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[AIResponse]:
        """Yield the next configured response round."""
        del tools, system_instruction, max_output_tokens
        self.stream_inputs.append(messages)
        if not self.streamed_rounds:
            raise AssertionError("no fake stream round configured")
        for response in self.streamed_rounds.pop(0):
            yield response

    async def list_models(self) -> list[str]:
        """Return one fake model without network access."""
        return ["fake-model"]


class FakeTool:
    """Callable local tool with optional deterministic failure."""

    def __init__(self, *, fail: bool = False) -> None:
        """Create a fake weather tool."""
        self.fail = fail
        self.calls: list[ToolCall] = []
        self.definition = ToolDefinition(
            id="weather",
            name="get_weather",
            description="Return fake weather.",
            parameters={
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
            is_builtin=True,
        )

    async def __call__(self, tool_call: ToolCall) -> object:
        """Return a local result or raise a configured tool failure."""
        self.calls.append(tool_call)
        if self.fail:
            raise RuntimeError("fake tool failure")
        return {"forecast": "sunny"}


def make_agent_def() -> AgentDefinition:
    """Build a minimal declaration for Harness tests."""
    return AgentDefinition(
        id="test-agent",
        name="Test Agent",
        description="Agent Harness test declaration.",
        system_prompt="Answer accurately.",
        provider_id="fake-provider",
        model="fake-model",
        tool_ids=["weather"],
    )


@pytest.fixture
def agent_def() -> AgentDefinition:
    """Provide a minimal test agent definition."""
    return make_agent_def()
