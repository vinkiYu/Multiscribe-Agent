"""ReAct Agent executor with an observable asynchronous event stream."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol
from uuid import uuid4

import structlog

from multiscribe_agent.agents.context import HarnessContext
from multiscribe_agent.agents.events import AgentEvent, AgentEventType
from multiscribe_agent.agents.prompt_service import PromptService
from multiscribe_agent.agents.reflector import Reflector
from multiscribe_agent.core.errors import ProviderError
from multiscribe_agent.domain.models import (
    AgentDefinition,
    AIResponse,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)
from multiscribe_agent.llm.provider import AIProvider
from multiscribe_agent.observability.meter import get_metrics_registry
from multiscribe_agent.observability.tracer import trace_span

type ProviderFactory = Callable[[AgentDefinition], AIProvider]
type ToolExecutor = Callable[[ToolCall], Awaitable[object]]
type ToolsOverride = tuple[list[ToolDefinition], ToolExecutor]

DEFAULT_MAX_ROUNDS = 5
DEFAULT_REFLECTOR_MAX_RETRIES = 1
log = structlog.get_logger(__name__)


class ToolRegistry(Protocol):
    """Minimal registry boundary that P5 can implement without coupling P4 to plugins."""

    def get_definitions(self, tool_ids: list[str]) -> list[ToolDefinition]:
        """Return definitions exposed to the current agent."""

    async def execute(self, tool_call: ToolCall) -> object:
        """Execute one local tool call and return serializable output."""


class AgentExecutor:
    """Execute a declaration through a bounded ReAct loop and emit typed events."""

    def __init__(
        self,
        provider_factory: ProviderFactory,
        tool_registry: ToolRegistry | None,
        prompt_service: PromptService,
        reflector: Reflector | None = None,
        *,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        reflector_max_retries: int = DEFAULT_REFLECTOR_MAX_RETRIES,
        token_budget: int = 120_000,
    ) -> None:
        """Configure provider/tool boundaries and bounded retry behavior.

        Raises:
            ValueError: If a round, retry, or token limit is invalid.
        """
        if max_rounds <= 0:
            raise ValueError("max_rounds must be positive")
        if reflector_max_retries < 0:
            raise ValueError("reflector_max_retries must not be negative")
        if token_budget <= 0:
            raise ValueError("token_budget must be positive")
        self._provider_factory = provider_factory
        self._tool_registry = tool_registry
        self._prompt_service = prompt_service
        self._reflector = reflector
        self._max_rounds = max_rounds
        self._reflector_max_retries = reflector_max_retries
        self._token_budget = token_budget

    async def run(
        self,
        agent_def: AgentDefinition,
        user_input: str,
        *,
        tools_override: ToolsOverride | None = None,
    ) -> AIResponse:
        """Collect an event stream and return its final provider-neutral response."""
        final_content = ""
        error_message = "agent run ended without final content"
        usage: TokenUsage | None = None
        async for event in self.stream(agent_def, user_input, tools_override=tools_override):
            if event.type == "final_content":
                final_content = str(event.data["content"])
            elif event.type == "error":
                error_message = str(event.data["message"])
            elif event.type == "usage":
                usage = TokenUsage(
                    input_tokens=self._event_int(event.data, "input_tokens"),
                    output_tokens=self._event_int(event.data, "output_tokens"),
                    total_tokens=self._event_int(event.data, "total_tokens"),
                )
        return AIResponse(content=final_content or error_message, usage=usage)

    async def stream(
        self,
        agent_def: AgentDefinition,
        user_input: str,
        *,
        tools_override: ToolsOverride | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Yield observable events for a bounded ReAct and reflection loop."""
        trace_id = uuid4().hex
        provider = self._provider_factory(agent_def)
        tools, tool_executor = self._resolve_tools(agent_def, tools_override)
        context = HarnessContext(
            self._build_system_prompt(agent_def), token_budget=self._token_budget
        )
        context.add_user(user_input)
        reflection_retries = 0

        for round_number in range(1, self._max_rounds + 1):
            yield self._event("round_start", {"round": round_number}, trace_id)
            content_parts: list[str] = []
            tool_calls: list[ToolCall] = []
            try:
                started = time.monotonic()
                with trace_span("llm.generate", {"agent_id": agent_def.id, "round": round_number}):
                    async for response in provider.stream(context.build_messages(), tools or None):
                        if response.content:
                            content_parts.append(response.content)
                            yield self._event(
                                "content",
                                {"content": response.content, "round": round_number},
                                trace_id,
                            )
                        if response.tool_calls:
                            tool_calls = response.tool_calls
                            yield self._event(
                                "tool_calls_delta",
                                {
                                    "tool_calls": self._dump_tool_calls(response.tool_calls),
                                    "round": round_number,
                                },
                                trace_id,
                            )
                        context.add_usage(response.usage)
                get_metrics_registry().record_llm_call(
                    context.usage_summary.total_tokens, time.monotonic() - started
                )
            except ProviderError as exc:
                log.warning(
                    "agent_provider_error",
                    agent_id=agent_def.id,
                    trace_id=trace_id,
                    error_type=type(exc).__name__,
                )
                yield self._event("error", {"message": str(exc), "round": round_number}, trace_id)
                return

            content = "".join(content_parts)
            context.add_assistant(content, tool_calls)
            usage = context.usage_summary
            yield self._event(
                "usage",
                {
                    "round": round_number,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                },
                trace_id,
            )

            if tool_calls:
                yield self._event(
                    "tool_calls",
                    {"tool_calls": self._dump_tool_calls(tool_calls), "round": round_number},
                    trace_id,
                )
                async for tool_event in self._execute_tools(
                    tool_calls,
                    tools,
                    tool_executor,
                    context,
                    round_number,
                    trace_id,
                ):
                    yield tool_event
                continue

            if self._reflector is not None and reflection_retries < self._reflector_max_retries:
                try:
                    reflection = await self._reflector.assess(user_input, content, provider)
                except (ProviderError, ValueError) as exc:
                    log.warning(
                        "agent_reflection_error",
                        agent_id=agent_def.id,
                        trace_id=trace_id,
                        error_type=type(exc).__name__,
                    )
                    yield self._event(
                        "error",
                        {"message": f"reflection failed: {exc}", "round": round_number},
                        trace_id,
                    )
                    return
                if reflection.should_retry:
                    reflection_retries += 1
                    feedback = self._prompt_service.render(
                        "common", "ReflectionFeedback", feedback=reflection.feedback
                    )
                    context.add_user(feedback)
                    continue

            yield self._event(
                "final_content", {"content": content, "round": round_number}, trace_id
            )
            return

        yield self._event(
            "error",
            {"message": f"maximum rounds reached ({self._max_rounds})", "round": self._max_rounds},
            trace_id,
        )

    async def _execute_tools(
        self,
        tool_calls: list[ToolCall],
        tools: list[ToolDefinition],
        tool_executor: ToolExecutor | None,
        context: HarnessContext,
        round_number: int,
        trace_id: str,
    ) -> AsyncIterator[AgentEvent]:
        available_names = {tool.name for tool in tools}
        for tool_call in tool_calls:
            dumped_call = tool_call.model_dump(mode="json")
            yield self._event(
                "tool_start",
                {"tool_call": dumped_call, "round": round_number},
                trace_id,
            )
            try:
                if tool_call.name not in available_names or tool_executor is None:
                    raise NotImplementedError(
                        f"non-local tool execution is deferred to P18: {tool_call.name}"
                    )
                with trace_span("tool.invoke", {"tool": tool_call.name}):
                    result = await tool_executor(tool_call)
                get_metrics_registry().record_tool_call(tool_call.name)
                serialized = self._serialize_tool_result(result)
            except Exception as exc:  # Tool plugins are an isolation boundary by design.
                log.warning(
                    "agent_tool_error",
                    tool_name=tool_call.name,
                    trace_id=trace_id,
                    error_type=type(exc).__name__,
                )
                error = str(exc)
                context.add_tool_result(tool_call.id, tool_call.name, f"[tool error] {error}")
                yield self._event(
                    "tool_error",
                    {"tool_call": dumped_call, "error": error, "round": round_number},
                    trace_id,
                )
                continue
            context.add_tool_result(tool_call.id, tool_call.name, serialized)
            yield self._event(
                "tool_result",
                {"tool_call": dumped_call, "result": serialized, "round": round_number},
                trace_id,
            )

    def _resolve_tools(
        self, agent_def: AgentDefinition, tools_override: ToolsOverride | None
    ) -> tuple[list[ToolDefinition], ToolExecutor | None]:
        if tools_override is not None:
            return tools_override
        if self._tool_registry is None:
            return [], None
        return self._tool_registry.get_definitions(agent_def.tool_ids), self._tool_registry.execute

    def _build_system_prompt(self, agent_def: AgentDefinition) -> str:
        from multiscribe_agent.skills.registry import get_skill_registry

        registry = get_skill_registry()
        blocks: list[str] = []
        for skill_id in agent_def.skill_ids:
            try:
                skill = registry.get(skill_id)
            except KeyError:
                blocks.append(f"- {skill_id} (not loaded)")
                continue
            blocks.append(
                f"- **{skill.name}** (id={skill.id})\n{skill.description}\n\n"
                f"{skill.instructions[:1500]}"
            )
        skill_prompt = "\n".join(blocks)
        return self._prompt_service.render(
            "common",
            "AgentSystem",
            system_prompt=agent_def.system_prompt,
            skill_prompt=skill_prompt,
        )

    @staticmethod
    def _serialize_tool_result(result: object) -> str:
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _dump_tool_calls(tool_calls: list[ToolCall]) -> list[dict[str, object]]:
        return [tool_call.model_dump(mode="json") for tool_call in tool_calls]

    @staticmethod
    def _event(event_type: AgentEventType, data: dict[str, object], trace_id: str) -> AgentEvent:
        return AgentEvent(type=event_type, data=data, trace_id=trace_id)

    @staticmethod
    def _event_int(data: dict[str, object], key: str) -> int:
        value = data[key]
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"event field must be an integer: {key}")
        return value
