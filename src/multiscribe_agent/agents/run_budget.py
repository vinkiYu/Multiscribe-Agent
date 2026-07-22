"""Hard run-level budgets for bounded Agent execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from multiscribe_agent.domain.models import TokenUsage

type BudgetKind = Literal[
    "context_tokens", "input_tokens", "output_tokens", "total_tokens", "llm_calls", "tool_calls"
]


@dataclass(frozen=True, slots=True)
class BudgetLimit:
    """One exhausted budget dimension."""

    kind: BudgetKind
    limit: int
    actual: int


class BudgetExhaustedError(RuntimeError):
    """Raised before further external work after a hard budget is exhausted."""

    def __init__(self, exhausted: BudgetLimit) -> None:
        self.exhausted = exhausted
        super().__init__(
            f"run budget exhausted: {exhausted.kind}={exhausted.actual} limit={exhausted.limit}"
        )


@dataclass(slots=True)
class RunBudget:
    """Track estimated/actual usage across an entire Agent run."""

    max_context_tokens: int = 120_000
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    max_total_tokens: int | None = None
    max_llm_calls: int | None = None
    max_tool_calls: int | None = None
    warning_ratio: float = 0.8
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    tool_calls: int = 0

    def __post_init__(self) -> None:
        values = (
            self.max_context_tokens,
            self.max_input_tokens,
            self.max_output_tokens,
            self.max_total_tokens,
            self.max_llm_calls,
            self.max_tool_calls,
        )
        if any(value is not None and value <= 0 for value in values):
            raise ValueError("run budget limits must be positive")
        if not 0 < self.warning_ratio <= 1:
            raise ValueError("warning_ratio must be in (0, 1]")

    def check_context(self, tokens: int) -> None:
        self._check("context_tokens", self.max_context_tokens, tokens)

    def before_llm(self) -> None:
        self._check("llm_calls", self.max_llm_calls, self.llm_calls + 1)
        self._check_before_token("input_tokens", self.max_input_tokens, self.input_tokens)
        self._check_before_token("output_tokens", self.max_output_tokens, self.output_tokens)
        self._check_before_token("total_tokens", self.max_total_tokens, self.total_tokens)
        self.llm_calls += 1

    def after_llm(self, usage: TokenUsage) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.total_tokens += usage.total_tokens
        self._check("input_tokens", self.max_input_tokens, self.input_tokens)
        self._check("output_tokens", self.max_output_tokens, self.output_tokens)
        self._check("total_tokens", self.max_total_tokens, self.total_tokens)

    def before_tool(self) -> None:
        self._check("tool_calls", self.max_tool_calls, self.tool_calls + 1)
        self.tool_calls += 1

    def warning(self) -> BudgetLimit | None:
        dimensions: tuple[tuple[BudgetKind, int | None, int], ...] = (
            ("input_tokens", self.max_input_tokens, self.input_tokens),
            ("output_tokens", self.max_output_tokens, self.output_tokens),
            ("total_tokens", self.max_total_tokens, self.total_tokens),
            ("llm_calls", self.max_llm_calls, self.llm_calls),
            ("tool_calls", self.max_tool_calls, self.tool_calls),
        )
        for kind, limit, actual in dimensions:
            if limit is not None and actual >= int(limit * self.warning_ratio):
                return BudgetLimit(kind, limit, actual)
        return None

    @staticmethod
    def _check(kind: BudgetKind, limit: int | None, actual: int) -> None:
        if limit is not None and actual > limit:
            raise BudgetExhaustedError(BudgetLimit(kind, limit, actual))

    @staticmethod
    def _check_before_token(kind: BudgetKind, limit: int | None, actual: int) -> None:
        if limit is not None and actual >= limit:
            raise BudgetExhaustedError(BudgetLimit(kind, limit, actual))
