"""Provider-aware token counting for Agent requests."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Protocol

from multiscribe_agent.domain.models import AIMessage, ToolDefinition


@dataclass(frozen=True, slots=True)
class TokenEstimate:
    """Estimated request tokens split by context partition."""

    total: int
    partitions: dict[str, int]
    degraded: bool = True
    reason: str | None = "tokenizer_unavailable"


class TokenCounter(Protocol):
    """Estimate provider request tokens, including tool schemas."""

    def count_text(self, text: str) -> int:
        """Count one text payload."""

    def count_request(
        self,
        messages: list[AIMessage],
        tools: list[ToolDefinition] | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> TokenEstimate: ...


class ConservativeTokenCounter:
    """Conservative fallback suitable for unknown models and proxy endpoints."""

    def __init__(self, *, chars_per_token: float = 1.5, message_overhead: int = 1) -> None:
        if chars_per_token <= 0:
            raise ValueError("chars_per_token must be positive")
        self._chars_per_token = chars_per_token
        self._message_overhead = message_overhead

    def count_text(self, text: str) -> int:
        """Estimate a text payload without requiring a tokenizer dependency."""
        return max(1, math.ceil(len(text) / self._chars_per_token) + self._message_overhead)

    def count_request(
        self,
        messages: list[AIMessage],
        tools: list[ToolDefinition] | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> TokenEstimate:
        """Count messages and serialized schemas in stable named partitions."""
        del provider, model
        partitions: dict[str, int] = {}
        for message in messages:
            payload = message.content
            if message.tool_calls:
                payload += json.dumps(
                    [call.model_dump(mode="json") for call in message.tool_calls],
                    ensure_ascii=False,
                    sort_keys=True,
                )
            partition = "system" if message.role == "system" else "history"
            partitions[partition] = partitions.get(partition, 0) + self.count_text(payload)
        if tools:
            schema = json.dumps(
                [tool.model_dump(mode="json") for tool in tools],
                ensure_ascii=False,
                sort_keys=True,
            )
            partitions["tool_schema"] = self.count_text(schema)
        return TokenEstimate(total=sum(partitions.values()), partitions=partitions)


class TiktokenCounter:
    """Count tokens with a model-aware tiktoken encoding."""

    def __init__(self, model: str | None = None) -> None:
        import tiktoken

        try:
            self._encoding = (
                tiktoken.encoding_for_model(model)
                if model
                else tiktoken.get_encoding("cl100k_base")
            )
        except KeyError:
            self._encoding = tiktoken.get_encoding("cl100k_base")

    def count_text(self, text: str) -> int:
        """Return the exact encoded token count for one text payload."""
        return len(self._encoding.encode(text))

    def count_request(
        self,
        messages: list[AIMessage],
        tools: list[ToolDefinition] | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> TokenEstimate:
        """Count message content, tool calls, and tool schemas in named partitions."""
        del provider, model
        partitions: dict[str, int] = {}
        for message in messages:
            payload = message.content
            if message.tool_calls:
                payload += json.dumps(
                    [call.model_dump(mode="json") for call in message.tool_calls],
                    ensure_ascii=False,
                    sort_keys=True,
                )
            partition = "system" if message.role == "system" else "history"
            partitions[partition] = partitions.get(partition, 0) + self.count_text(payload)
        if tools:
            schema = json.dumps(
                [tool.model_dump(mode="json") for tool in tools],
                ensure_ascii=False,
                sort_keys=True,
            )
            partitions["tool_schema"] = self.count_text(schema)
        return TokenEstimate(
            total=sum(partitions.values()),
            partitions=partitions,
            degraded=False,
            reason=None,
        )


def resolve_token_counter(provider: str | None, model: str | None) -> TokenCounter:
    """Return precise tiktoken counting, falling back conservatively if unavailable."""
    del provider
    try:
        return TiktokenCounter(model)
    except ImportError:
        return ConservativeTokenCounter(chars_per_token=1.5)
