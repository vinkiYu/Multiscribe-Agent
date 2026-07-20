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
    "final_content",
    "error",
    "usage",
    "loop_detected",
    "budget_warning",
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
        usage: ``round`` plus ``input_tokens``, ``output_tokens``, and ``total_tokens``.
        error: ``message`` and optional ``round``.
        loop_detected: ``tool``, ``args_hash``, ``consecutive_repeats``, and ``round``.
        budget_warning: ``used_tokens``, ``budget``, ``remaining``, and ``round``.
    """

    type: AgentEventType
    data: dict[str, object]
    trace_id: str
