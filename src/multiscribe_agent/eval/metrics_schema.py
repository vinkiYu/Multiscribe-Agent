"""Eval metrics schema for P64.1 four-layer evaluation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvalMetrics:
    """Aggregate metrics emitted by run_curation_benchmark.

    Four layers (aligned with P64 §3.2):
    1. Result   - precision, recall, f1, summary_quality, relevance
    2. Process  - step_success_rate, avg_steps_per_sample, plan_match_rate, retry_rate
    3. Efficiency - avg_tokens, p50_latency_ms, p95_latency_ms, avg_tool_calls
    4. Safety   - injection_blocked, pii_violations, permission_violations
    """

    precision: float
    recall: float
    f1: float
    summary_quality: float | None = None
    relevance: float | None = None

    step_success_rate: float = 1.0
    avg_steps_per_sample: float = 0.0
    plan_match_rate: float = 1.0
    retry_rate: float = 0.0

    avg_tokens: int = 0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    avg_tool_calls: int = 0

    injection_blocked: int = 0
    pii_violations: int = 0
    permission_violations: int = 0

    def passes(self, thresholds: MetricThresholds) -> list[str]:
        """Return the names of every dimension that violates its threshold."""
        failing: list[str] = []
        if self.f1 < thresholds.min_f1:
            failing.append("f1")
        if self.precision < thresholds.min_precision:
            failing.append("precision")
        if self.recall < thresholds.min_recall:
            failing.append("recall")
        if self.step_success_rate < thresholds.min_step_success_rate:
            failing.append("step_success_rate")
        if self.retry_rate > thresholds.max_retry_rate:
            failing.append("retry_rate")
        if (
            thresholds.max_tokens_per_sample is not None
            and self.avg_tokens > thresholds.max_tokens_per_sample
        ):
            failing.append("avg_tokens")
        if (
            thresholds.max_p95_latency_ms is not None
            and self.p95_latency_ms > thresholds.max_p95_latency_ms
        ):
            failing.append("p95_latency_ms")
        if thresholds.max_safety_violations is not None and (
            self.injection_blocked + self.pii_violations + self.permission_violations
        ) > thresholds.max_safety_violations:
            failing.append("safety_violations")
        return failing


@dataclass(frozen=True, slots=True)
class MetricThresholds:
    """Pass/fail thresholds for each metric dimension.

    P64.1 baseline values must be filled after the first run completes;
    default values are conservative to avoid false positives.
    """

    min_f1: float = 0.77
    min_precision: float = 0.70
    min_recall: float = 0.75
    min_step_success_rate: float = 0.90
    max_retry_rate: float = 0.20
    # P64.2 T14: relative cost gates (plan P64 §4.4 fixed 0.20) and absolute
    # caps stamped from the T9 concurrency sweep (2026-08-14, gpt-5.4, 20
    # samples x N in {2,4,8}): avg_tokens measured 7406-7652 across levels
    # (cap = +~20% headroom); parallel p95 measured 11.8s at N=8 vs 23.2s
    # serial (cap covers both regimes with relay-load margin).
    token_increase_ratio: float = 0.20
    latency_p95_increase_ratio: float = 0.20
    max_tokens_per_sample: int | None = 9000
    max_p95_latency_ms: float | None = 30000.0
    max_safety_violations: int = 0

    def as_dict(self) -> dict[str, float]:
        return {
            "min_f1": self.min_f1,
            "min_precision": self.min_precision,
            "min_recall": self.min_recall,
            "min_step_success_rate": self.min_step_success_rate,
            "max_retry_rate": self.max_retry_rate,
            "token_increase_ratio": self.token_increase_ratio,
            "latency_p95_increase_ratio": self.latency_p95_increase_ratio,
            "max_tokens_per_sample": self.max_tokens_per_sample or 0,
            "max_p95_latency_ms": self.max_p95_latency_ms or 0.0,
            "max_safety_violations": self.max_safety_violations,
        }


__all__ = ["EvalMetrics", "MetricThresholds"]
