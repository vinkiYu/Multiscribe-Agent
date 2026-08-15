"""Per-sample step trace aggregator for P64.1 four-layer eval.

The evaluation harness invokes `run_curation` directly and never emits
`workflow.events` (those are only published by the workflow engine).  This
collector captures per-sample traces by being called from inside
`run_curation_benchmark` (T2) with the sample id and step outcomes.

P64.2 T13 adds `on_event` so real `workflow.events` streams (keyed by
`trace_id`) feed the same aggregation, giving multi-step workflows a
discriminating step_success_rate while the single-step ("curate",) harness
path stays as the fallback.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass, field

from multiscribe_agent.agents.workflow.events import WorkflowEvent


@dataclass(frozen=True, slots=True)
class SampleTrace:
    """One benchmark sample's step record."""

    sample_id: str
    steps_planned: list[str] = field(default_factory=list)
    steps_completed: list[str] = field(default_factory=list)
    retry_count: int = 0


class TraceCollector:
    """Aggregate per-sample step traces during a benchmark run."""

    def __init__(self) -> None:
        self._traces: dict[str, SampleTrace] = {}

    def start_sample(self, sample_id: str, planned_steps: Iterable[str] | None = None) -> None:
        """Begin recording a sample; optionally accept the planned step ids."""
        self._traces[sample_id] = SampleTrace(
            sample_id=sample_id,
            steps_planned=list(planned_steps) if planned_steps else [],
        )

    def record_step_complete(self, sample_id: str, step_id: str) -> None:
        if sample_id in self._traces:
            self._traces[sample_id].steps_completed.append(step_id)

    def record_retry(self, sample_id: str, count: int = 1) -> None:
        trace = self._traces.get(sample_id)
        if trace is not None:
            object.__setattr__(trace, "retry_count", trace.retry_count + count)

    def end_sample(self, sample_id: str) -> SampleTrace:
        return self._traces[sample_id]

    def all_traces(self) -> list[SampleTrace]:
        """Return every recorded trace (used by the P64.2 trace sink)."""
        return list(self._traces.values())

    async def consume(self, events: AsyncIterable[WorkflowEvent]) -> None:
        """Consume a real ``WorkflowEngine.stream()`` event iterator."""
        async for event in events:
            self.on_event(event)

    def on_event(self, event: WorkflowEvent) -> None:
        """Consume one workflow event; step_start counts as one planned step."""
        if event.type == "step_start":
            self._ensure(event.trace_id).steps_planned.append(str(event.data.get("step_id", "")))
        elif event.type == "step_complete":
            self._ensure(event.trace_id).steps_completed.append(str(event.data.get("step_id", "")))
        elif event.type == "step_error":
            self._ensure(event.trace_id)  # an errored step never completes
        elif event.type == "loop_iteration":
            retry = event.data.get("retry", 1)
            count = int(retry) if isinstance(retry, (int, float)) else 1
            self.record_retry(event.trace_id, count)

    def _ensure(self, trace_id: str) -> SampleTrace:
        if trace_id not in self._traces:
            self._traces[trace_id] = SampleTrace(sample_id=trace_id)
        return self._traces[trace_id]

    def aggregate(self) -> tuple[float, float, float, float]:
        """Compute (step_success_rate, avg_steps, plan_match_rate, retry_rate)."""
        if not self._traces:
            return (1.0, 0.0, 1.0, 0.0)
        traces = list(self._traces.values())
        total_planned = sum(len(t.steps_planned) for t in traces) or len(traces)
        total_completed = sum(len(t.steps_completed) for t in traces)
        total_retries = sum(t.retry_count for t in traces)
        step_success = total_completed / total_planned if total_planned else 1.0
        avg_steps = total_completed / len(traces)
        plan_match_count = sum(
            1
            for t in traces
            if t.steps_planned and set(t.steps_completed).issubset(set(t.steps_planned))
        )
        plan_match = plan_match_count / len(traces) if any(t.steps_planned for t in traces) else 1.0
        retry_rate = total_retries / len(traces)
        return (step_success, avg_steps, plan_match, retry_rate)


__all__ = ["SampleTrace", "TraceCollector"]
