"""OpenAI implementation of the provider-neutral LLM contract."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx
import structlog
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from multiscribe_agent.config import ProviderConfig
from multiscribe_agent.core.errors import ProviderError
from multiscribe_agent.domain.models import AIMessage, AIResponse, ToolCall, ToolDefinition
from multiscribe_agent.llm.provider import (
    from_lc_message,
    merge_tool_call_deltas,
    to_lc_bindable_tools,
    to_lc_messages,
)

REQUEST_TIMEOUT_SECONDS = 60.0
log = structlog.get_logger(__name__)


class OpenAIProvider:
    """Generate OpenAI chat completions through LangChain without exposing its types."""

    def __init__(
        self,
        config: ProviderConfig,
        model: str,
        temperature: float,
        proxy: str | None = None,
    ) -> None:
        """Create an OpenAI chat model bound to one configured model id.

        Raises:
            ProviderError: If this endpoint has no API key.
        """
        if not config.api_key:
            raise ProviderError(f"no api key configured for provider {config.id}")
        self._config = config
        self._http_client = httpx.AsyncClient(proxy=proxy) if proxy else None
        self._llm: BaseChatModel = ChatOpenAI(
            model=model,
            api_key=config.api_key,
            temperature=temperature,
            base_url=config.base_url or None,
            http_async_client=self._http_client,
        )

    async def generate(
        self,
        messages: list[AIMessage],
        tools: list[ToolDefinition] | None = None,
        system_instruction: str | None = None,
    ) -> AIResponse:
        """Generate one complete OpenAI response with a bounded wait time."""
        model = self._llm.bind_tools(to_lc_bindable_tools(tools)) if tools else self._llm
        try:
            response = await asyncio.wait_for(
                model.ainvoke(to_lc_messages(messages, system_instruction)),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            log.warning("openai_request_timeout", provider_id=self._config.id)
            raise ProviderError("OpenAI request timed out") from exc
        except (httpx.HTTPError, OSError) as exc:
            log.warning(
                "openai_request_failed", provider_id=self._config.id, error_type=type(exc).__name__
            )
            raise ProviderError("OpenAI request failed") from exc
        return from_lc_message(response)

    async def list_models(self) -> list[str]:
        """Return models declared by this endpoint configuration."""
        return list(self._config.models)

    async def stream(
        self,
        messages: list[AIMessage],
        tools: list[ToolDefinition] | None = None,
        system_instruction: str | None = None,
    ) -> AsyncIterator[AIResponse]:
        """Stream response chunks and accumulate fragmented tool-call arguments."""
        model = self._llm.bind_tools(to_lc_bindable_tools(tools)) if tools else self._llm
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
            log.warning("openai_stream_timeout", provider_id=self._config.id)
            raise ProviderError("OpenAI stream timed out") from exc
        except (httpx.HTTPError, OSError) as exc:
            log.warning(
                "openai_stream_failed", provider_id=self._config.id, error_type=type(exc).__name__
            )
            raise ProviderError("OpenAI stream failed") from exc
