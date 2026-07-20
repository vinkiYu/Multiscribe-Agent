"""Optional benchmark for workflow DAG topological sorting."""

import pytest

pytest.importorskip("pytest_benchmark")

from multiscribe_agent.agents.workflow.graph import build_graph, topological_levels
from multiscribe_agent.domain.models import WorkflowDefinition, WorkflowStep


@pytest.mark.benchmark
def test_topological_sort_50_nodes(benchmark) -> None:
    """Kahn sorting remains bounded for a 50-node linear DAG."""
    steps = [
        WorkflowStep(
            id=f"step-{index}",
            name=f"Step {index}",
            step_type="agent",
            agent_id="agent",
            next_step_id=f"step-{index + 1}" if index < 49 else None,
        )
        for index in range(50)
    ]
    graph = build_graph(WorkflowDefinition(id="bench", name="Bench", description="", steps=steps))
    benchmark(topological_levels, graph)
