"""Anthropic implementation of the provider-neutral LLM contract."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import cast

import httpx
import structlog
from anthropic import AnthropicError
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel

from multiscribe_agent.config import ProviderConfig
from multiscribe_agent.core.errors import ProviderError
from multiscribe_agent.domain.models import AIMessage, AIResponse, ToolCall, ToolDefinition
from multiscribe_agent.llm.provider import (
    from_lc_message,
    merge_tool_call_deltas,
    normalize_provider_error,
    to_lc_bindable_tools,
    to_lc_messages,
)

REQUEST_TIMEOUT_SECONDS = 60.0
log = structlog.get_logger(__name__)


class AnthropicProvider:
    """Generate Anthropic chat completions through LangChain without exposing its types."""

    def __init__(
        self,
        config: ProviderConfig,
        model: str,
        temperature: float,
        proxy: str | None = None,
    ) -> None:
        """Create an Anthropic chat model bound to one configured model id.

        Raises:
            ProviderError: If this endpoint has no API key.
        """
        if not config.api_key:
            raise ProviderError(f"no api key configured for provider {config.id}")
        self._config = config
        self._model = model
        self._llm: BaseChatModel = ChatAnthropic(
            model=model,
            api_key=config.api_key,
            temperature=temperature,
            base_url=config.base_url or None,
            anthropic_proxy=proxy,
        )

    async def generate(
        self,
        messages: list[AIMessage],
        tools: list[ToolDefinition] | None = None,
        system_instruction: str | None = None,
        max_output_tokens: int | None = None,
    ) -> AIResponse:
        """Generate one complete Anthropic response with a bounded wait time."""
        model = self._model_for_call(tools, max_output_tokens)
        try:
            response = await asyncio.wait_for(
                model.ainvoke(to_lc_messages(messages, system_instruction)),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            log.warning("anthropic_request_timeout", provider_id=self._config.id)
            raise ProviderError("Anthropic request timed out") from exc
        except (AnthropicError, httpx.HTTPError, OSError) as exc:
            log.warning(
                "anthropic_request_failed",
                provider_id=self._config.id,
                error_type=type(exc).__name__,
            )
            raise normalize_provider_error(exc, "Anthropic") from exc
        return from_lc_message(response)

    async def list_models(self) -> list[str]:
        """Return models declared by this endpoint configuration."""
        return list(self._config.models)

    async def stream(
        self,
        messages: list[AIMessage],
        tools: list[ToolDefinition] | None = None,
        system_instruction: str | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[AIResponse]:
        """Stream response chunks and accumulate fragmented tool-call arguments."""
        model = self._model_for_call(tools, max_output_tokens)
        accumulated_calls: list[ToolCall] = []
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                async for chunk in model.astream(to_lc_messages(messages, system_instruction)):
                    response = from_lc_message(chunk)
                    accumulated_calls = merge_tool_call_deltas(
                        accumulated_calls, response.tool_calls
                    )
                    yield response.model_copy(update={"tool_calls": accumulated_calls})
        except TimeoutError as exc:
            log.warning("anthropic_stream_timeout", provider_id=self._config.id)
            raise ProviderError("Anthropic stream timed out") from exc
        except (AnthropicError, httpx.HTTPError, OSError) as exc:
            log.warning(
                "anthropic_stream_failed",
                provider_id=self._config.id,
                error_type=type(exc).__name__,
            )
            raise normalize_provider_error(exc, "Anthropic") from exc

    @property
    def context_window_tokens(self) -> int:
        return self._config.model_context_window(self._model)

    @property
    def default_output_tokens(self) -> int:
        return self._config.model_output_tokens(self._model)

    def _model_for_call(
        self, tools: list[ToolDefinition] | None, max_output_tokens: int | None
    ) -> BaseChatModel:
        model = self._llm.bind_tools(to_lc_bindable_tools(tools)) if tools else self._llm
        if max_output_tokens:
            return cast(BaseChatModel, model.bind(max_tokens=max_output_tokens))
        return cast(BaseChatModel, model)
