"""Workflow dependency graph construction and Kahn ordering."""

from __future__ import annotations

from dataclasses import dataclass

from multiscribe_agent.core.errors import WorkflowError
from multiscribe_agent.domain.models import WorkflowDefinition, WorkflowStep


@dataclass(frozen=True, slots=True)
class WorkflowGraph:
    """Normalized dependency graph for one workflow definition."""

    steps: dict[str, WorkflowStep]
    edges: list[tuple[str, str]]
    successors: dict[str, list[str]]
    predecessors: dict[str, list[str]]


def build_graph(workflow: WorkflowDefinition) -> WorkflowGraph:
    """Combine explicit transitions and input-map references into dependency edges."""
    steps = {step.id: step for step in workflow.steps}
    if len(steps) != len(workflow.steps):
        raise WorkflowError("workflow step IDs must be unique")
    edges: set[tuple[str, str]] = set()
    for step in workflow.steps:
        targets = [step.next_step_id, *(step.next_step_ids or [])]
        for target in targets:
            if target is not None:
                _add_edge(edges, steps, step.id, target)
        for source in (step.input_map or {}).values():
            if source != "start":
                _add_edge(edges, steps, source, step.id)
    successors: dict[str, list[str]] = {step_id: [] for step_id in steps}
    predecessors: dict[str, list[str]] = {step_id: [] for step_id in steps}
    for source, target in sorted(edges):
        successors[source].append(target)
        predecessors[target].append(source)
    return WorkflowGraph(steps, sorted(edges), successors, predecessors)


def detect_cycle(graph: WorkflowGraph) -> list[str] | None:
    """Return one concrete cycle path, or ``None`` when the graph is acyclic."""
    visiting: set[str] = set()
    visited: set[str] = set()
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        """Walk successors and retain the active DFS path for cycle reporting."""
        if node in visiting:
            return [*path[path.index(node) :], node]
        if node in visited:
            return None
        visiting.add(node)
        path.append(node)
        for successor in graph.successors[node]:
            cycle = visit(successor)
            if cycle is not None:
                return cycle
        path.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for step_id in sorted(graph.steps):
        cycle = visit(step_id)
        if cycle is not None:
            return cycle
    return None


def topological_levels(graph: WorkflowGraph) -> list[list[str]]:
    """Return Kahn levels, or raise if a cycle exists."""
    levels = _kahn_levels(graph)
    if levels is None:
        raise WorkflowError(f"workflow cycle detected: {detect_cycle(graph)}")
    return levels


def _kahn_levels(graph: WorkflowGraph) -> list[list[str]] | None:
    """Compute dependency-free execution levels without mutating the graph."""
    indegree = {node: len(predecessors) for node, predecessors in graph.predecessors.items()}
    ready = sorted(node for node, count in indegree.items() if count == 0)
    levels: list[list[str]] = []
    completed = 0
    while ready:
        level = ready
        levels.append(level)
        completed += len(level)
        next_ready: list[str] = []
        for node in level:
            for child in graph.successors[node]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    next_ready.append(child)
        ready = sorted(next_ready)
    return levels if completed == len(graph.steps) else None


def _add_edge(
    edges: set[tuple[str, str]], steps: dict[str, WorkflowStep], source: str, target: str
) -> None:
    """Validate and add one dependency edge."""
    if source not in steps or target not in steps:
        raise WorkflowError(f"workflow edge references unknown step: {source} -> {target}")
    edges.add((source, target))
