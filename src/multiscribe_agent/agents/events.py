"""Typed events emitted by the Agent Harness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

type AgentEventType = Literal[
    "round_start",
    "content",
    "tool_calls_delta",
    "tool_calls",
    "tool_start",
    "tool_result",
    "tool_error",
    "approval_required",
    "final_content",
    "error",
    "usage",
    "loop_detected",
    "budget_warning",
    "budget_exhausted",
    "context_pressure",
    "context_compacted",
    "context_degraded",
    "context_budget_exhausted",
]


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """One observable event from an Agent run.

    Event data schemas:
        round_start: ``round``.
        content/final_content: ``content`` and ``round``.
        tool_calls_delta/tool_calls: ``tool_calls`` and ``round``.
        tool_start: ``tool_call`` and ``round``.
        tool_result: ``tool_call``, ``result``, and ``round``.
        tool_error: ``tool_call``, ``error``, and ``round``.
        approval_required: redacted ``tool_call``, ``error``, and ``round``.
        usage: ``round`` plus ``input_tokens``, ``output_tokens``, and ``total_tokens``.
        error: ``message`` and optional ``round``.
        loop_detected: ``tool``, ``args_hash``, ``consecutive_repeats``, and ``round``.
        budget_warning: ``used_tokens``, ``budget``, ``remaining``, and ``round``.
        context_pressure/context_compacted: token partitions plus model-window budget metadata.
        context_budget_exhausted: actual/effective tokens, partitions, compaction stages,
            retry count, and an actionable message.
    """

    type: AgentEventType
    data: dict[str, object]
    trace_id: str
