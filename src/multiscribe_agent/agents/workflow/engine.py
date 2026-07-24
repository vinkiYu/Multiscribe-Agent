"""Asynchronous generic DAG workflow execution."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol
from uuid import uuid4

from multiscribe_agent.agents.workflow.events import WorkflowEvent
from multiscribe_agent.agents.workflow.graph import build_graph, topological_levels
from multiscribe_agent.agents.workflow.loop_node import execute_loop_step
from multiscribe_agent.agents.workflow.protocols import AgentStepExecutor, LoopReflector
from multiscribe_agent.core.errors import AgentStepTerminalError, WorkflowError
from multiscribe_agent.domain.models import WorkflowDefinition, WorkflowStep

DEFAULT_WORKFLOW_TIMEOUT_SECONDS = 300.0


class WorkflowStore(Protocol):
    """Read workflow definition documents by ID."""

    async def get(self, table: str, entity_id: str) -> dict[str, object] | None:
        """Return one persisted workflow document."""


class WorkflowEngine:
    """Execute definition-driven workflows through an injected agent boundary."""

    def __init__(
        self,
        executor: AgentStepExecutor,
        workflow_store: WorkflowStore,
        reflector: LoopReflector | None = None,
    ) -> None:
        self._executor = executor
        self._workflow_store = workflow_store
        self._reflector = reflector

    async def run(
        self,
        workflow_id: str,
        input_data: object,
        *,
        date: str | None = None,
        timeout: float = DEFAULT_WORKFLOW_TIMEOUT_SECONDS,
    ) -> dict[str, object]:
        """Return completed step outputs and final output."""
        outputs: dict[str, object] = {}
        final = input_data
        async for event in self.stream(workflow_id, input_data, date=date, timeout=timeout):
            if event.type == "workflow_error":
                raise WorkflowError(str(event.data["message"]), event.data)
            if event.type == "step_complete":
                outputs[str(event.data["step_id"])] = event.data["output"]
            if event.type == "workflow_complete":
                final = event.data["final"]
        return {"step_results": outputs, "final": final}

    async def stream(
        self,
        workflow_id: str,
        input_data: object,
        *,
        date: str | None = None,
        timeout: float = DEFAULT_WORKFLOW_TIMEOUT_SECONDS,
    ) -> AsyncIterator[WorkflowEvent]:
        """Yield workflow and step lifecycle events in topological order."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        del date
        raw = await self._workflow_store.get("workflows", workflow_id)
        if raw is None:
            raise WorkflowError(f"workflow not found: {workflow_id}")
        trace_id = uuid4().hex
        results: dict[str, object] = {"start": input_data}
        yield WorkflowEvent(
            "workflow_start", {"workflow_id": workflow_id, "timeout": timeout}, trace_id
        )
        try:
            graph = build_graph(WorkflowDefinition.model_validate(raw))
            levels = topological_levels(graph)
        except WorkflowError as exc:
            yield WorkflowEvent("workflow_error", {"message": str(exc)}, trace_id)
            return
        deadline = asyncio.get_running_loop().time() + timeout
        try:
            for level in levels:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError
                executions: list[tuple[WorkflowStep, object]] = []
                for step_id in level:
                    step = graph.steps[step_id]
                    step_input = self._input(step, graph.predecessors[step_id], results)
                    executions.append((step, step_input))
                    yield WorkflowEvent("step_start", {"step_id": step_id}, trace_id)
                outcomes = await asyncio.wait_for(
                    asyncio.gather(
                        *(
                            self._execute_step(step, step_input, trace_id, remaining)
                            for step, step_input in executions
                        ),
                        return_exceptions=True,
                    ),
                    timeout=remaining,
                )
                for (step, _), outcome in zip(executions, outcomes, strict=True):
                    if isinstance(outcome, BaseException):
                        terminal_data: dict[str, object] = {}
                        if isinstance(outcome, AgentStepTerminalError):
                            terminal_data = {
                                "terminal_type": outcome.terminal_type,
                                "terminal_data": outcome.terminal_data,
                            }
                        error_data = {
                            "step_id": step.id,
                            "message": str(outcome),
                            **terminal_data,
                        }
                        yield WorkflowEvent("step_error", error_data, trace_id)
                        yield WorkflowEvent("workflow_error", error_data, trace_id)
                        return
                    output, loop_history = outcome
                    results[step.id] = output
                    for iteration in loop_history:
                        yield WorkflowEvent(
                            "loop_iteration", {"step_id": step.id, **iteration}, trace_id
                        )
                    yield WorkflowEvent(
                        "step_complete", {"step_id": step.id, "output": output}, trace_id
                    )
                    if self._is_empty(output) and graph.successors[step.id]:
                        message = (
                            f"step {step.id} produced an empty output with downstream successors"
                        )
                        yield WorkflowEvent("workflow_error", {"message": message}, trace_id)
                        return
        except TimeoutError:
            message = f"Workflow Timeout: execution exceeded {timeout}s"
            yield WorkflowEvent(
                "workflow_error", {"message": message, "timeout": timeout}, trace_id
            )
            return
        yield WorkflowEvent(
            "workflow_complete",
            {"workflow_id": workflow_id, "final": self._final(graph, results, input_data)},
            trace_id,
        )

    async def _execute_step(
        self, step: WorkflowStep, value: object, trace_id: str, timeout: float
    ) -> tuple[object, list[dict[str, object]]]:
        """Execute one enabled agent or nested-workflow step."""
        if not step.enabled:
            return value, []
        if step.step_type == "workflow":
            if step.workflow_id is None:
                raise WorkflowError("workflow step requires workflow_id")
            return (await self.run(step.workflow_id, value, timeout=timeout))["final"], []
        if step.agent_id is None:
            raise WorkflowError("agent step requires agent_id")
        if step.max_iterations is not None:
            output, history = await execute_loop_step(
                step,
                str(value),
                self._executor,
                self._reflector,
                trace_id=trace_id,
            )
            return output, history
        return await self._executor.execute(step.agent_id, str(value)), []

    @staticmethod
    def _input(step: WorkflowStep, predecessors: list[str], results: dict[str, object]) -> object:
        """Derive step input from named mapping or zero/one/many predecessors."""
        if step.input_map is not None:
            mapped = {key: results[source] for key, source in step.input_map.items()}
            return next(iter(mapped.values())) if len(mapped) == 1 else mapped
        if not predecessors:
            return results["start"]
        if len(predecessors) == 1:
            return results[predecessors[0]]
        return {step_id: results[step_id] for step_id in predecessors}

    @staticmethod
    def _is_empty(value: object) -> bool:
        """Return whether a step result cannot meaningfully feed a successor."""
        return value is None or (isinstance(value, str) and not value.strip())

    @staticmethod
    def _final(graph: object, results: dict[str, object], input_data: object) -> object:
        """Return a sink result, preserving all terminal branches when needed."""
        if not hasattr(graph, "successors"):
            raise WorkflowError("invalid workflow graph")
        sinks = [step_id for step_id, children in graph.successors.items() if not children]
        if not sinks:
            return input_data
        if len(sinks) == 1:
            return results[sinks[0]]
        return {step_id: results[step_id] for step_id in sinks}
