"""ReAct Agent executor with an observable asynchronous event stream."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Literal, Protocol
from uuid import uuid4

import structlog

from multiscribe_agent.agents.artifacts import InMemoryArtifactStore
from multiscribe_agent.agents.context import ContextBudgetError, ContextPriority, HarnessContext
from multiscribe_agent.agents.context_provider import ContextProvider
from multiscribe_agent.agents.events import AgentEvent, AgentEventType
from multiscribe_agent.agents.prompt_service import PromptService
from multiscribe_agent.agents.reflector import REFLECTOR_INSTRUCTION, Reflector
from multiscribe_agent.agents.run_budget import BudgetExhaustedError, RunBudget
from multiscribe_agent.agents.token_counter import TokenCounter, resolve_token_counter
from multiscribe_agent.core.errors import (
    ProviderContextLengthError,
    ProviderError,
    ToolApprovalRequired,
)
from multiscribe_agent.domain.models import (
    AgentDefinition,
    AgentRunResult,
    AIMessage,
    AIResponse,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)
from multiscribe_agent.llm.provider import AIProvider
from multiscribe_agent.observability.meter import get_metrics_registry
from multiscribe_agent.observability.tracer import trace_span
from multiscribe_agent.plugins.security import redact_data, redact_text

type ProviderFactory = Callable[[AgentDefinition], AIProvider]
type ToolExecutor = Callable[[ToolCall], Awaitable[object]]
type ToolsOverride = tuple[list[ToolDefinition], ToolExecutor]

DEFAULT_MAX_ROUNDS = 5
DEFAULT_REFLECTOR_MAX_RETRIES = 1
DEFAULT_MODEL_WINDOW_TOKENS = 128_000
DEFAULT_OUTPUT_TOKENS = 4_096
CONTEXT_SAFETY_RATIO = 0.05
MIN_CONTEXT_SAFETY_TOKENS = 512
PROVIDER_RETRY_BUDGET_RATIO = 0.85
MAX_SKILL_PROMPT_CHARS = 4_000
DEADLOCK_WINDOW = 3
DEADLOCK_MAX_REPEATS = 3
log = structlog.get_logger(__name__)


class ToolRegistry(Protocol):
    """Minimal registry boundary that P5 can implement without coupling P4 to plugins."""

    def get_definitions(self, tool_ids: list[str]) -> list[ToolDefinition]:
        """Return definitions exposed to the current agent."""

    async def execute(self, tool_call: ToolCall, *, approval_token: str | None = None) -> object:
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
        max_input_tokens: int | None = None,
        max_output_tokens: int | None = None,
        max_total_tokens: int | None = None,
        max_llm_calls: int | None = None,
        max_tool_calls: int | None = None,
        context_provider: ContextProvider | None = None,
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
        self._max_input_tokens = max_input_tokens
        self._max_output_tokens = max_output_tokens
        self._max_total_tokens = max_total_tokens
        self._max_llm_calls = max_llm_calls
        self._max_tool_calls = max_tool_calls
        self._context_provider = context_provider

    async def run(
        self,
        agent_def: AgentDefinition,
        user_input: str,
        *,
        tools_override: ToolsOverride | None = None,
        memory_summaries: list[str] | None = None,
        approval_tokens: Sequence[str] | None = None,
    ) -> AIResponse:
        """Collect an event stream and return its final provider-neutral response."""
        result = await self.run_result(
            agent_def,
            user_input,
            tools_override=tools_override,
            memory_summaries=memory_summaries,
            approval_tokens=approval_tokens,
        )
        return AIResponse(
            content=result.content,
            usage=result.usage,
            raw={"status": result.status, "terminal_data": result.terminal_data},
        )

    async def run_result(
        self,
        agent_def: AgentDefinition,
        user_input: str,
        *,
        tools_override: ToolsOverride | None = None,
        memory_summaries: list[str] | None = None,
        approval_tokens: Sequence[str] | None = None,
    ) -> AgentRunResult:
        """Collect the event stream without discarding structured terminal states."""
        final_content = ""
        error_message = "agent run ended without final content"
        usage: TokenUsage | None = None
        status: Literal["success", "budget_exhausted", "context_budget_exhausted", "error"] = (
            "error"
        )
        terminal_data: dict[str, object] | None = None
        async for event in self.stream(
            agent_def,
            user_input,
            tools_override=tools_override,
            memory_summaries=memory_summaries,
            approval_tokens=approval_tokens,
        ):
            if event.type == "final_content":
                final_content = str(event.data["content"])
                if status not in {"budget_exhausted", "context_budget_exhausted"}:
                    status = "success"
            elif event.type == "error":
                error_message = str(event.data["message"])
                status = "error"
                terminal_data = dict(event.data)
            elif event.type in {"budget_exhausted", "context_budget_exhausted"}:
                status = event.type
                terminal_data = dict(event.data)
                error_message = str(
                    event.data.get(
                        "message",
                        "Context budget exhausted. Reduce input, tools, or retrieved context.",
                    )
                )
            elif event.type == "usage":
                usage = TokenUsage(
                    input_tokens=self._event_int(event.data, "input_tokens"),
                    output_tokens=self._event_int(event.data, "output_tokens"),
                    total_tokens=self._event_int(event.data, "total_tokens"),
                )
        return AgentRunResult(
            status=status,
            content=final_content or error_message,
            usage=usage,
            terminal_data=terminal_data,
        )

    async def stream(
        self,
        agent_def: AgentDefinition,
        user_input: str,
        *,
        tools_override: ToolsOverride | None = None,
        memory_summaries: list[str] | None = None,
        approval_tokens: Sequence[str] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Yield observable events for a bounded ReAct and reflection loop."""
        trace_id = uuid4().hex
        provider = self._provider_factory(agent_def)
        tools, tool_executor = self._resolve_tools(agent_def, tools_override, approval_tokens or ())
        token_counter = resolve_token_counter(agent_def.provider_id, agent_def.model)
        model_window = int(getattr(provider, "context_window_tokens", DEFAULT_MODEL_WINDOW_TOKENS))
        output_reserve = agent_def.max_output_tokens or int(
            getattr(provider, "default_output_tokens", DEFAULT_OUTPUT_TOKENS)
        )
        tool_schema_tokens = token_counter.count_request(
            [], tools or None, model=agent_def.model, provider=agent_def.provider_id
        ).partitions.get("tool_schema", 0)
        safety_margin = max(MIN_CONTEXT_SAFETY_TOKENS, int(model_window * CONTEXT_SAFETY_RATIO))
        context_limit = min(self._token_budget, model_window)
        message_budget = context_limit - output_reserve - tool_schema_tokens - safety_margin
        run_budget = RunBudget(
            max_context_tokens=context_limit,
            max_input_tokens=self._max_input_tokens,
            max_output_tokens=self._max_output_tokens,
            max_total_tokens=self._max_total_tokens,
            max_llm_calls=self._max_llm_calls,
            max_tool_calls=self._max_tool_calls,
        )
        context = HarnessContext(
            self._build_system_prompt(agent_def),
            token_budget=max(1, message_budget),
            token_counter=token_counter,
            artifact_store=InMemoryArtifactStore(),
        )
        budget_metadata: dict[str, object] = {
            "model_window": model_window,
            "context_limit": context_limit,
            "message_budget": message_budget,
            "output_reserve": output_reserve,
            "tool_schema_tokens": tool_schema_tokens,
            "safety_margin": safety_margin,
            "reserved_tokens": output_reserve + safety_margin,
            "retry_count": 0,
        }
        if message_budget <= 0:
            exc = ContextBudgetError(
                tool_schema_tokens + output_reserve + safety_margin,
                context_limit,
                {"system": 0, "history": 0, "tool_schema": tool_schema_tokens},
                ["minimum_context_unresolvable"],
            )
            yield self._context_budget_event(exc, 0, trace_id, budget_metadata)
            return
        if self._context_provider is not None:
            try:
                retrieved = await self._context_provider.retrieve(user_input, agent_id=agent_def.id)
                for summary in retrieved.memories:
                    context.inject_memory(summary)
                context.inject_knowledge(retrieved.knowledge)
                if any(reason.endswith(":degraded") for reason in retrieved.reasons):
                    get_metrics_registry().record_context_event("degraded")
                    yield self._event(
                        "context_degraded",
                        {"reasons": retrieved.reasons, "round": 0},
                        trace_id,
                    )
            except Exception as exc:  # Context enrichment must not block the primary task.
                get_metrics_registry().record_context_event("degraded")
                log.warning(
                    "agent_context_provider_degraded",
                    agent_id=agent_def.id,
                    trace_id=trace_id,
                    error_type=type(exc).__name__,
                )
                yield self._event(
                    "context_degraded",
                    {"reasons": ["context_provider:degraded"], "round": 0},
                    trace_id,
                )
        for summary in memory_summaries or []:
            context.inject_memory(summary)
        try:
            context.add_user(user_input, priority=ContextPriority.REQUIRED)
        except ContextBudgetError as exc:
            yield self._context_budget_event(exc, 0, trace_id, budget_metadata)
            return
        reflection_retries = 0
        recent_tool_calls: list[tuple[str, str]] = []

        for round_number in range(1, self._max_rounds + 1):
            try:
                request_messages = context.build_messages()
                estimate = token_counter.count_request(
                    request_messages,
                    tools or None,
                    model=agent_def.model,
                    provider=agent_def.provider_id,
                )
                run_budget.check_context(estimate.total)
                run_budget.before_llm()
            except ContextBudgetError as exc:
                yield self._context_budget_event(exc, round_number, trace_id, budget_metadata)
                return
            except BudgetExhaustedError as exc:
                yield self._budget_event(exc, round_number, trace_id)
                return
            message_tokens = estimate.partitions.get("system", 0) + estimate.partitions.get(
                "history", 0
            )
            if message_tokens >= int(context.token_budget * 0.8):
                yield self._event(
                    "budget_warning",
                    {
                        "used_tokens": message_tokens,
                        "budget": context.token_budget,
                        "remaining": max(0, context.token_budget - message_tokens),
                        "request_tokens": estimate.total,
                        "round": round_number,
                        **budget_metadata,
                    },
                    trace_id,
                )
                yield self._event(
                    "context_pressure",
                    {
                        "tokens": message_tokens,
                        "request_tokens": estimate.total,
                        "budget": context.token_budget,
                        "partitions": estimate.partitions,
                        "round": round_number,
                        **budget_metadata,
                    },
                    trace_id,
                )
            if context.last_compaction:
                get_metrics_registry().record_context_event("compacted")
                yield self._event(
                    "context_compacted",
                    {**context.last_compaction, "round": round_number, **budget_metadata},
                    trace_id,
                )
            yield self._event("round_start", {"round": round_number}, trace_id)
            content_parts: list[str] = []
            tool_calls: list[ToolCall] = []
            round_usage: TokenUsage | None = None
            retry_count = 0
            remaining_output = run_budget.remaining_output_tokens()
            call_output_limit = (
                min(output_reserve, remaining_output)
                if remaining_output is not None
                else output_reserve
            )
            try:
                started = time.monotonic()
                while True:
                    try:
                        with trace_span(
                            "llm.generate", {"agent_id": agent_def.id, "round": round_number}
                        ):
                            async for response in provider.stream(
                                request_messages,
                                tools or None,
                                max_output_tokens=call_output_limit,
                            ):
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
                                            "tool_calls": self._dump_tool_calls(
                                                response.tool_calls
                                            ),
                                            "round": round_number,
                                        },
                                        trace_id,
                                    )
                                if response.usage is not None:
                                    round_usage = response.usage
                        if retry_count:
                            get_metrics_registry().record_provider_context_event("retry_success")
                        break
                    except ProviderContextLengthError:
                        get_metrics_registry().record_provider_context_event("rejected")
                        if content_parts or tool_calls or retry_count >= 1:
                            raise
                        retry_count = 1
                        get_metrics_registry().record_provider_context_event("retry")
                        retry_budget = max(1, int(message_budget * PROVIDER_RETRY_BUDGET_RATIO))
                        context.apply_aggressive_budget(retry_budget)
                        request_messages = context.build_messages()
                        estimate = token_counter.count_request(
                            request_messages,
                            tools or None,
                            model=agent_def.model,
                            provider=agent_def.provider_id,
                        )
                        run_budget.check_context(estimate.total)
                        run_budget.before_llm()
                        budget_metadata["message_budget"] = retry_budget
                        budget_metadata["retry_count"] = retry_count
                        yield self._event(
                            "context_compacted",
                            {
                                "round": round_number,
                                "compaction_stage": "provider_retry_aggressive",
                                "compaction_stages": context.compaction_stages,
                                **budget_metadata,
                            },
                            trace_id,
                        )
                if round_usage is None:
                    output_estimate = token_counter.count_text("".join(content_parts))
                    round_usage = TokenUsage(
                        input_tokens=estimate.total,
                        output_tokens=output_estimate,
                        total_tokens=estimate.total + output_estimate,
                    )
                context.add_usage(round_usage)
                run_budget.after_llm(round_usage)
                get_metrics_registry().record_llm_call(
                    context.usage_summary.total_tokens, time.monotonic() - started
                )
            except ProviderContextLengthError as exc:
                log.warning(
                    "agent_provider_context_rejected",
                    agent_id=agent_def.id,
                    trace_id=trace_id,
                    model_window=model_window,
                    message_budget=budget_metadata["message_budget"],
                    output_reserve=output_reserve,
                    tool_schema_tokens=tool_schema_tokens,
                    compaction_stage=(context.compaction_stages[-1:] or ["none"])[0],
                    retry_count=retry_count,
                )
                if content_parts or tool_calls:
                    yield self._event(
                        "error", {"message": str(exc), "round": round_number}, trace_id
                    )
                    return
                terminal = ContextBudgetError(
                    estimate.partitions.get("system", 0) + estimate.partitions.get("history", 0),
                    context.token_budget,
                    estimate.partitions,
                    context.compaction_stages,
                )
                yield self._context_budget_event(terminal, round_number, trace_id, budget_metadata)
                return
            except ProviderError as exc:
                log.warning(
                    "agent_provider_error",
                    agent_id=agent_def.id,
                    trace_id=trace_id,
                    error_type=type(exc).__name__,
                )
                yield self._event("error", {"message": str(exc), "round": round_number}, trace_id)
                return
            except BudgetExhaustedError as exc:
                yield self._budget_event(exc, round_number, trace_id)
                return
            except ContextBudgetError as exc:
                yield self._context_budget_event(exc, round_number, trace_id, budget_metadata)
                return

            content = "".join(content_parts)
            context.mark_current_round_consumed()
            context.add_assistant(
                content,
                tool_calls,
                priority=ContextPriority.REQUIRED if tool_calls else ContextPriority.NORMAL,
            )
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
                for tool_call in tool_calls:
                    signature = self._tool_call_signature(tool_call)
                    recent_tool_calls.append(signature)
                    if len(recent_tool_calls) > DEADLOCK_WINDOW:
                        recent_tool_calls.pop(0)
                    if (
                        len(recent_tool_calls) == DEADLOCK_MAX_REPEATS
                        and len(set(recent_tool_calls)) == 1
                    ):
                        yield self._event(
                            "loop_detected",
                            {
                                "tool": tool_call.name,
                                "args_hash": signature[1],
                                "consecutive_repeats": DEADLOCK_MAX_REPEATS,
                                "round": round_number,
                            },
                            trace_id,
                        )
                        return
                yield self._event(
                    "tool_calls",
                    {"tool_calls": self._dump_tool_calls(tool_calls), "round": round_number},
                    trace_id,
                )
                budget_stopped = False
                async for tool_event in self._execute_tools(
                    tool_calls,
                    tools,
                    tool_executor,
                    context,
                    run_budget,
                    round_number,
                    trace_id,
                ):
                    yield tool_event
                    budget_stopped = tool_event.type == "budget_exhausted"
                if budget_stopped:
                    return
                continue

            if self._reflector is not None and reflection_retries < self._reflector_max_retries:
                try:
                    remaining_output = run_budget.remaining_output_tokens()
                    reflection_output_limit = min(
                        512,
                        output_reserve,
                        remaining_output if remaining_output is not None else output_reserve,
                    )
                    reflection_input_tokens = self._reflection_input_tokens(
                        user_input, content, token_counter
                    )
                    run_budget.before_llm()
                    reflection_started = time.monotonic()
                    reflection = await self._reflector.assess(
                        user_input,
                        content,
                        provider,
                        max_output_tokens=reflection_output_limit,
                    )
                    reflection_usage = reflection.usage or self._estimate_reflection_usage(
                        user_input, content, reflection, token_counter
                    )
                    context.add_usage(reflection_usage)
                    run_budget.after_llm(reflection_usage)
                    get_metrics_registry().record_llm_call(
                        reflection_usage.total_tokens,
                        time.monotonic() - reflection_started,
                    )
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
                except BudgetExhaustedError as exc:
                    yield self._budget_event(exc, round_number, trace_id)
                    yield self._event(
                        "final_content", {"content": content, "round": round_number}, trace_id
                    )
                    return
                except (ProviderError, ValueError) as exc:
                    failure_output_tokens = (
                        reflection_output_limit if isinstance(exc, ValueError) else 0
                    )
                    failure_usage = TokenUsage(
                        input_tokens=reflection_input_tokens,
                        output_tokens=failure_output_tokens,
                        total_tokens=reflection_input_tokens + failure_output_tokens,
                    )
                    context.add_usage(failure_usage)
                    try:
                        run_budget.after_llm(failure_usage)
                    except BudgetExhaustedError as budget_exc:
                        yield self._budget_event(budget_exc, round_number, trace_id)
                        yield self._event(
                            "final_content",
                            {"content": content, "round": round_number},
                            trace_id,
                        )
                        return
                    get_metrics_registry().record_llm_call(
                        failure_usage.total_tokens,
                        time.monotonic() - reflection_started,
                    )
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
                    remaining_output = run_budget.remaining_output_tokens()
                    if remaining_output is not None and remaining_output < output_reserve:
                        yield self._event(
                            "budget_exhausted",
                            {
                                "budget_type": "output_tokens",
                                "limit": run_budget.max_output_tokens or 0,
                                "actual": run_budget.output_tokens,
                                "round": round_number,
                                "message": (
                                    "Output budget exhausted; returning the best current result."
                                ),
                            },
                            trace_id,
                        )
                        yield self._event(
                            "final_content", {"content": content, "round": round_number}, trace_id
                        )
                        return
                    reflection_retries += 1
                    feedback = self._prompt_service.render(
                        "common", "ReflectionFeedback", feedback=reflection.feedback
                    )
                    context.add_user(feedback, important=True)
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
        run_budget: RunBudget,
        round_number: int,
        trace_id: str,
    ) -> AsyncIterator[AgentEvent]:
        available_names = {tool.name for tool in tools}
        for tool_call in tool_calls:
            try:
                run_budget.before_tool()
            except BudgetExhaustedError as exc:
                yield self._budget_event(exc, round_number, trace_id)
                return
            dumped_call = redact_data(tool_call.model_dump(mode="json"))
            if not isinstance(dumped_call, dict):
                raise TypeError("redacted tool call must remain an object")
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
            except ToolApprovalRequired as exc:
                error = redact_text(str(exc))
                context.add_tool_result(
                    tool_call.id,
                    tool_call.name,
                    "[tool blocked: operator approval required]",
                    priority=ContextPriority.REQUIRED,
                )
                yield self._event(
                    "approval_required",
                    {"tool_call": dumped_call, "error": error, "round": round_number},
                    trace_id,
                )
                continue
            except Exception as exc:  # Tool plugins are an isolation boundary by design.
                log.warning(
                    "agent_tool_error",
                    tool_name=tool_call.name,
                    trace_id=trace_id,
                    error_type=type(exc).__name__,
                )
                error = redact_text(str(exc))
                context.add_tool_result(
                    tool_call.id,
                    tool_call.name,
                    f"[tool error] {error}",
                    priority=ContextPriority.REQUIRED,
                )
                yield self._event(
                    "tool_error",
                    {"tool_call": dumped_call, "error": error, "round": round_number},
                    trace_id,
                )
                continue
            serialized = redact_text(serialized)
            context.add_tool_result(
                tool_call.id,
                tool_call.name,
                serialized,
                priority=ContextPriority.REQUIRED,
            )
            yield self._event(
                "tool_result",
                {"tool_call": dumped_call, "result": serialized, "round": round_number},
                trace_id,
            )

    def _resolve_tools(
        self,
        agent_def: AgentDefinition,
        tools_override: ToolsOverride | None,
        approval_tokens: Sequence[str],
    ) -> tuple[list[ToolDefinition], ToolExecutor | None]:
        if tools_override is not None:
            return tools_override
        if self._tool_registry is None:
            return [], None
        registry = self._tool_registry

        async def execute_with_approval(tool_call: ToolCall) -> object:
            last_error: ToolApprovalRequired | None = None
            for token in approval_tokens:
                try:
                    return await registry.execute(tool_call, approval_token=token)
                except ToolApprovalRequired as exc:
                    last_error = exc
            if last_error is not None:
                raise last_error
            return await registry.execute(tool_call)

        return registry.get_definitions(agent_def.tool_ids), execute_with_approval

    def _build_system_prompt(self, agent_def: AgentDefinition) -> str:
        from multiscribe_agent.skills.registry import get_skill_registry

        registry = get_skill_registry()
        blocks: list[str] = []
        total_chars = 0
        for skill_id in agent_def.skill_ids:
            try:
                skill = registry.get(skill_id)
            except KeyError:
                block = f"- {skill_id} (not loaded)"
            else:
                block = (
                    f"- **{skill.name}** (id={skill.id})\n{skill.description}\n\n"
                    f"{skill.instructions[:1500]}"
                )
            separator = "\n" if blocks else ""
            remaining = MAX_SKILL_PROMPT_CHARS - total_chars - len(separator)
            if remaining <= 0:
                break
            if len(block) > remaining:
                suffix = "\n...[truncated]"
                if remaining > len(suffix):
                    blocks.append(block[: remaining - len(suffix)] + suffix)
                break
            blocks.append(block)
            total_chars += len(separator) + len(block)
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
    def _estimate_reflection_usage(
        task: str,
        output: str,
        reflection: object,
        token_counter: TokenCounter,
    ) -> TokenUsage:
        input_tokens = AgentExecutor._reflection_input_tokens(task, output, token_counter)
        response_payload = json.dumps(
            {
                "quality": getattr(reflection, "quality", ""),
                "score": getattr(reflection, "score", 0),
                "feedback": getattr(reflection, "feedback", ""),
            },
            ensure_ascii=False,
        )
        output_tokens = token_counter.count_text(response_payload)
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

    @staticmethod
    def _reflection_input_tokens(
        task: str,
        output: str,
        token_counter: TokenCounter,
    ) -> int:
        request = [
            AIMessage(role="system", content=REFLECTOR_INSTRUCTION),
            AIMessage(role="user", content=f"Task:\n{task}\n\nOutput:\n{output}"),
        ]
        return token_counter.count_request(request).total

    @staticmethod
    def _dump_tool_calls(tool_calls: list[ToolCall]) -> list[dict[str, object]]:
        redacted = redact_data([tool_call.model_dump(mode="json") for tool_call in tool_calls])
        if not isinstance(redacted, list):
            raise TypeError("redacted tool calls must remain a list")
        return [item for item in redacted if isinstance(item, dict)]

    @staticmethod
    def _tool_call_signature(tool_call: ToolCall) -> tuple[str, str]:
        """Return a bounded signature used to identify repeated tool calls."""
        arguments = json.dumps(
            tool_call.arguments,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        args_hash = hashlib.sha256(arguments.encode("utf-8")).hexdigest()[:16]
        return tool_call.name, args_hash

    @staticmethod
    def _event(event_type: AgentEventType, data: dict[str, object], trace_id: str) -> AgentEvent:
        return AgentEvent(type=event_type, data=data, trace_id=trace_id)

    @staticmethod
    def _budget_event(exc: BudgetExhaustedError, round_number: int, trace_id: str) -> AgentEvent:
        get_metrics_registry().record_context_event("budget_exhausted")
        exhausted = exc.exhausted
        return AgentEvent(
            type="budget_exhausted",
            data={
                "budget_type": exhausted.kind,
                "limit": exhausted.limit,
                "actual": exhausted.actual,
                "round": round_number,
            },
            trace_id=trace_id,
        )

    @staticmethod
    def _context_budget_event(
        exc: ContextBudgetError,
        round_number: int,
        trace_id: str,
        metadata: dict[str, object] | None = None,
    ) -> AgentEvent:
        get_metrics_registry().record_context_event("budget_exhausted")
        partitions = dict(exc.partitions)
        tool_schema_tokens = (metadata or {}).get("tool_schema_tokens")
        if isinstance(tool_schema_tokens, int):
            partitions["tool_schema"] = tool_schema_tokens
        safe_metadata = metadata or {}
        message_tokens = partitions.get("system", 0) + partitions.get("history", 0)
        request_tokens = message_tokens + partitions.get("tool_schema", 0)
        reserved_tokens = safe_metadata.get("reserved_tokens", 0)
        context_limit = safe_metadata.get("context_limit")
        window_actual = (
            request_tokens + reserved_tokens if isinstance(reserved_tokens, int) else request_tokens
        )
        window_limit = context_limit if isinstance(context_limit, int) else exc.budget
        log.warning(
            "agent_context_budget_exhausted",
            actual_tokens=window_actual,
            effective_budget=window_limit,
            system_tokens=partitions.get("system", 0),
            history_tokens=partitions.get("history", 0),
            tool_schema_tokens=partitions.get("tool_schema", 0),
            model_window=safe_metadata.get("model_window"),
            message_budget=safe_metadata.get("message_budget"),
            output_reserve=safe_metadata.get("output_reserve"),
            compaction_stage=(exc.compaction_stages[-1:] or ["none"])[0],
            retry_count=safe_metadata.get("retry_count", 0),
        )
        return AgentEvent(
            type="context_budget_exhausted",
            data={
                "budget_type": "context_tokens",
                "limit": window_limit,
                "actual": window_actual,
                "partitions": partitions,
                "message_tokens": message_tokens,
                "request_tokens": request_tokens,
                "compaction_stages": exc.compaction_stages,
                "message": (
                    "Context budget exhausted. Reduce input content, enabled tools, or knowledge "
                    "recall, or configure a model with a larger context window."
                ),
                "round": round_number,
                **safe_metadata,
            },
            trace_id=trace_id,
        )

    @staticmethod
    def _event_int(data: dict[str, object], key: str) -> int:
        value = data[key]
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"event field must be an integer: {key}")
        return value
