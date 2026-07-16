"""Tests for workflow dependency graph construction."""

import pytest

from multiscribe_agent.agents.workflow.graph import build_graph, detect_cycle, topological_levels
from multiscribe_agent.core.errors import WorkflowError
from multiscribe_agent.domain.models import WorkflowDefinition, WorkflowStep


def _workflow(*steps: WorkflowStep) -> WorkflowDefinition:
    """Build a compact workflow definition for graph tests."""
    return WorkflowDefinition(id="workflow", name="Workflow", description="", steps=list(steps))


def _step(step_id: str, **kwargs: object) -> WorkflowStep:
    """Build one agent step with optional graph fields."""
    return WorkflowStep(id=step_id, name=step_id, step_type="agent", agent_id=step_id, **kwargs)


def test_build_graph_combines_explicit_and_input_map_edges() -> None:
    """Both explicit edge shapes and data references become dependencies."""
    graph = build_graph(
        _workflow(
            _step("a", next_step_id="b"),
            _step("b", next_step_ids=["c"]),
            _step("c", input_map={"source": "a", "initial": "start"}),
        )
    )

    assert graph.edges == [("a", "b"), ("a", "c"), ("b", "c")]
    assert graph.predecessors["c"] == ["a", "b"]


def test_detect_cycle_returns_concrete_cycle() -> None:
    """A directed cycle is reported with its closing node."""
    graph = build_graph(
        _workflow(
            _step("a", next_step_id="b"), _step("b", next_step_id="c"), _step("c", next_step_id="a")
        )
    )

    assert detect_cycle(graph) == ["a", "b", "c", "a"]
    with pytest.raises(WorkflowError, match="cycle"):
        topological_levels(graph)


def test_topological_levels_keep_disabled_steps_and_parallel_branches() -> None:
    """Disabled nodes stay in the graph and independent nodes share a level."""
    graph = build_graph(
        _workflow(
            _step("a", next_step_ids=["b", "c"]),
            _step("b", enabled=False, next_step_id="d"),
            _step("c", next_step_id="d"),
            _step("d"),
        )
    )

    assert topological_levels(graph) == [["a"], ["b", "c"], ["d"]]
    assert graph.steps["b"].enabled is False
