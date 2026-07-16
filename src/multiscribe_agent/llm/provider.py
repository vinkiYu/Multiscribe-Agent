"""Provider-neutral LLM contracts, normalization helpers, and factory."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from typing import Protocol, cast

from langchain_core.messages import (
    AIMessage as LCAIMessage,
)
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from multiscribe_agent.config import ProviderConfig
from multiscribe_agent.core.errors import ProviderError
from multiscribe_agent.domain.models import (
    AIMessage,
    AIResponse,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)


class AIProvider(Protocol):
    """Common asynchronous interface implemented by every configured LLM provider."""

    async def generate(
        self,
        messages: list[AIMessage],
        tools: list[ToolDefinition] | None = None,
        system_instruction: str | None = None,
    ) -> AIResponse:
        """Generate one complete response from a fixed provider model."""

    def stream(
        self,
        messages: list[AIMessage],
        tools: list[ToolDefinition] | None = None,
        system_instruction: str | None = None,
    ) -> AsyncIterator[AIResponse]:
        """Yield response deltas from a fixed provider model."""

    async def list_models(self) -> list[str]:
        """Return the locally configured models without making a network request."""


def to_lc_messages(
    messages: list[AIMessage], system_instruction: str | None = None
) -> list[BaseMessage]:
    """Convert provider-neutral messages into LangChain message objects.

    Args:
        messages: Conversation messages in the domain representation.
        system_instruction: Optional system prompt prepended to the conversation.

    Returns:
        LangChain message instances preserving roles and tool-call metadata.
    """
    result: list[BaseMessage] = []
    if system_instruction:
        result.append(SystemMessage(content=system_instruction))

    for message in messages:
        if message.role == "user":
            result.append(HumanMessage(content=message.content, name=message.name))
        elif message.role == "assistant":
            result.append(
                LCAIMessage(
                    content=message.content,
                    name=message.name,
                    tool_calls=[
                        _to_lc_tool_call(tool_call) for tool_call in message.tool_calls or []
                    ],
                )
            )
        elif message.role == "system":
            result.append(SystemMessage(content=message.content, name=message.name))
        else:
            result.append(
                ToolMessage(
                    content=message.content,
                    tool_call_id=message.tool_call_id or "",
                    name=message.name,
                )
            )
    return result


def from_lc_message(message: BaseMessage) -> AIResponse:
    """Normalize a LangChain message or chunk into an ``AIResponse``.

    List-valued multimodal content is encoded as JSON so image URL blocks and other
    structured provider content are retained by the string-valued domain contract.

    Args:
        message: A LangChain response message or streamed response chunk.

    Returns:
        A provider-neutral completion response.
    """
    tool_calls = [_from_lc_tool_call(tool_call) for tool_call in _read_tool_calls(message)]
    return AIResponse(
        content=_normalize_content(message.content),
        tool_calls=tool_calls,
        usage=_read_usage(message),
    )


def normalize_tools(tools: list[ToolDefinition]) -> list[dict[str, object]]:
    """Convert domain tool definitions into LangChain ``bind_tools`` dictionaries.

    Args:
        tools: Tool metadata supplied by the agent runtime.

    Returns:
        Tool dictionaries with the provider-independent schema field.
    """
    return [
        {"name": tool.name, "description": tool.description, "schema": tool.parameters}
        for tool in tools
    ]


def to_lc_bindable_tools(tools: list[ToolDefinition]) -> list[dict[str, object]]:
    """Adapt normalized tools to the LangChain provider binding shape.

    LangChain's OpenAI and Anthropic integrations both consume ``parameters`` at
    bind time, while the public normalizer keeps the ``schema`` contract used by
    the provider-neutral API.

    Args:
        tools: Tool metadata supplied by the agent runtime.

    Returns:
        Tool dictionaries accepted by LangChain's ``bind_tools`` methods.
    """
    return [
        {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["schema"],
        }
        for tool in normalize_tools(tools)
    ]


def merge_tool_call_deltas(existing: list[ToolCall], incoming: list[ToolCall]) -> list[ToolCall]:
    """Merge streaming tool-call fragments by id or name.

    String arguments are concatenated because LangChain emits JSON arguments in
    fragments for several providers. Mapping arguments are merged shallowly.

    Args:
        existing: Tool calls accumulated from preceding stream chunks.
        incoming: Tool calls normalized from the current stream chunk.

    Returns:
        A new complete-or-partial accumulated tool-call list.
    """
    merged = list(existing)
    for tool_call in incoming:
        index = _find_tool_call(merged, tool_call)
        if index is None:
            merged.append(tool_call)
            continue

        current = merged[index]
        merged[index] = ToolCall(
            id=tool_call.id or current.id,
            name=tool_call.name or current.name,
            arguments=_merge_arguments(current.arguments, tool_call.arguments),
        )
    return merged


def create_provider(
    config: ProviderConfig,
    *,
    model: str | None = None,
    temperature: float | None = None,
    proxy: str | None = None,
) -> AIProvider:
    """Create a concrete provider with a model selected at construction time.

    Args:
        config: Endpoint configuration selected by provider id.
        model: Per-agent model override.
        temperature: Per-agent sampling temperature.
        proxy: Optional HTTP proxy for the provider client.

    Returns:
        The requested OpenAI or Anthropic provider implementation.

    Raises:
        ProviderError: If no model is configured or the provider type is unknown.
        NotImplementedError: If the optional Google or Ollama implementation is requested.
    """
    resolved_model = model if model is not None else (config.models[0] if config.models else None)
    if not resolved_model:
        raise ProviderError(f"no model configured for provider {config.id}")
    resolved_temperature = temperature if temperature is not None else 0.7

    if config.type == "openai":
        from multiscribe_agent.llm.providers.openai import OpenAIProvider

        return OpenAIProvider(config, resolved_model, resolved_temperature, proxy)
    if config.type == "anthropic":
        from multiscribe_agent.llm.providers.anthropic import AnthropicProvider

        return AnthropicProvider(config, resolved_model, resolved_temperature, proxy)
    if config.type in {"google", "ollama"}:
        raise NotImplementedError(f"{config.type} provider is deferred to P18")
    raise ProviderError(f"unknown provider type: {config.type}")


def _to_lc_tool_call(tool_call: ToolCall) -> dict[str, object]:
    """Convert one domain tool call to LangChain's canonical representation."""
    arguments = tool_call.arguments
    if isinstance(arguments, str):
        try:
            decoded = json.loads(arguments)
        except json.JSONDecodeError:
            decoded = {}
        arguments = decoded if isinstance(decoded, dict) else {}
    return {"id": tool_call.id, "name": tool_call.name, "args": arguments, "type": "tool_call"}


def _normalize_content(content: object) -> str:
    """Return text content while preserving multimodal lists as JSON."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _read_tool_calls(message: BaseMessage) -> list[Mapping[str, object]]:
    """Read regular or streamed tool calls from a LangChain message."""
    raw_chunks = getattr(message, "tool_call_chunks", None)
    # AIMessageChunk may omit incomplete JSON from tool_calls but preserves it here.
    raw_calls = raw_chunks if raw_chunks else getattr(message, "tool_calls", None)
    if not isinstance(raw_calls, list):
        return []
    return [call for call in raw_calls if isinstance(call, Mapping)]


def _from_lc_tool_call(tool_call: Mapping[str, object]) -> ToolCall:
    """Convert one LangChain tool-call mapping into the domain representation."""
    arguments = tool_call.get("args", tool_call.get("arguments", {}))
    if not isinstance(arguments, dict | str):
        arguments = {}
    return ToolCall(
        id=str(tool_call.get("id", "")),
        name=str(tool_call.get("name", "")),
        arguments=cast(dict[str, object] | str, arguments),
    )


def _read_usage(message: BaseMessage) -> TokenUsage | None:
    """Normalize LangChain usage metadata across provider response formats."""
    usage_metadata = getattr(message, "usage_metadata", None)
    usage = usage_metadata if isinstance(usage_metadata, Mapping) else None
    if usage is None:
        response_metadata = getattr(message, "response_metadata", None)
        if isinstance(response_metadata, Mapping):
            candidate = response_metadata.get("token_usage")
            usage = candidate if isinstance(candidate, Mapping) else None
    if usage is None:
        return None

    input_tokens = _read_int(usage, "input_tokens", "prompt_tokens")
    output_tokens = _read_int(usage, "output_tokens", "completion_tokens")
    total_tokens = _read_int(usage, "total_tokens")
    if input_tokens is None or output_tokens is None:
        return None
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens if total_tokens is not None else input_tokens + output_tokens,
    )


def _read_int(metadata: Mapping[str, object], *keys: str) -> int | None:
    """Read the first integer value available under the given metadata keys."""
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, int):
            return value
    return None


def _find_tool_call(tool_calls: list[ToolCall], target: ToolCall) -> int | None:
    """Find a matching accumulated call using the stable id, then the name."""
    for index, tool_call in enumerate(tool_calls):
        if target.id and tool_call.id == target.id:
            return index
        if target.name and tool_call.name == target.name:
            return index
    return None


def _merge_arguments(
    left: dict[str, object] | str, right: dict[str, object] | str
) -> dict[str, object] | str:
    """Combine structured arguments or concatenate stream fragments."""
    if isinstance(left, str) and isinstance(right, str):
        return left + right
    if isinstance(left, dict) and isinstance(right, dict):
        return left | right
    return right
