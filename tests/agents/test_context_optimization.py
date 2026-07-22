"""Focused regression tests for the context optimization backlog."""

from __future__ import annotations

import json

import pytest
from conftest import FakeProvider, FakeTool

from multiscribe_agent.agents.artifacts import InMemoryArtifactStore
from multiscribe_agent.agents.checkpoint import ConversationCheckpoint
from multiscribe_agent.agents.context import HarnessContext
from multiscribe_agent.agents.context_provider import RetrievedContext
from multiscribe_agent.agents.executor import AgentExecutor
from multiscribe_agent.agents.prompt_service import PromptService
from multiscribe_agent.agents.run_budget import BudgetExhaustedError, RunBudget
from multiscribe_agent.agents.token_counter import ConservativeTokenCounter
from multiscribe_agent.domain.models import (
    AIMessage,
    AIResponse,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)


def test_token_counter_includes_tool_schema_partition() -> None:
    counter = ConservativeTokenCounter()
    tool = ToolDefinition(
        id="search",
        name="search",
        description="Search",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
    )

    estimate = counter.count_request([AIMessage(role="user", content="find it")], [tool])

    assert estimate.partitions["tool_schema"] > 0
    assert estimate.total == sum(estimate.partitions.values())


def test_run_budget_stops_before_call_after_exact_total_limit() -> None:
    budget = RunBudget(max_context_tokens=100, max_total_tokens=10)
    budget.before_llm()
    budget.after_llm(TokenUsage(input_tokens=7, output_tokens=3, total_tokens=10))

    with pytest.raises(BudgetExhaustedError):
        budget.before_llm()


def test_large_json_uses_valid_preview_and_artifact_reference() -> None:
    store = InMemoryArtifactStore()
    context = HarnessContext("system", tool_result_limit=500, artifact_store=store)
    original = json.dumps([{"id": index, "value": "x" * 80} for index in range(20)])

    context.add_tool_result("call-json", "search", original)
    preview = context.messages[-1].content

    payload, reference = preview.rsplit("\n[artifact_ref=", 1)
    assert json.loads(payload)["total"] == 20
    artifact_id = reference.rstrip("]")
    assert store.get(artifact_id, limit=len(original)) == original


def test_checkpoint_retains_goal_decision_and_tool_evidence() -> None:
    checkpoint = ConversationCheckpoint.from_groups(
        [
            [AIMessage(role="user", content="Do not include financing news")],
            [AIMessage(role="assistant", content="Use only technical sources")],
        ]
    )

    rendered = checkpoint.render()
    assert "Current goal: Do not include financing news" in rendered
    assert "Assistant conclusion: Use only technical sources" in rendered


class _ContextProvider:
    async def retrieve(self, query: str, *, agent_id: str) -> RetrievedContext:
        assert query == "question"
        assert agent_id == "test-agent"
        return RetrievedContext(["memory"], ["knowledge"], ["memory:fts"])


@pytest.mark.asyncio
async def test_executor_automatically_injects_generic_retrieved_context(agent_def) -> None:
    provider = FakeProvider([[AIResponse(content="answer")]])
    executor = AgentExecutor(
        lambda _: provider,
        None,
        PromptService(),
        context_provider=_ContextProvider(),
    )

    await executor.run(agent_def, "question")

    system = provider.stream_inputs[0][0].content
    assert "[Memory Data]" in system
    assert "memory" in system
    assert "[Knowledge Data]" in system
    assert "knowledge" in system


@pytest.mark.asyncio
async def test_tool_call_budget_prevents_external_execution(agent_def) -> None:
    calls = [
        ToolCall(id="call-1", name="get_weather", arguments={"city": "Beijing"}),
        ToolCall(id="call-2", name="get_weather", arguments={"city": "Shanghai"}),
    ]
    provider = FakeProvider([[AIResponse(content="", tool_calls=calls)]])
    tool = FakeTool()
    executor = AgentExecutor(
        lambda _: provider,
        None,
        PromptService(),
        max_tool_calls=1,
    )

    events = [
        event
        async for event in executor.stream(
            agent_def,
            "question",
            tools_override=([tool.definition], tool),
        )
    ]

    assert len(tool.calls) == 1
    assert events[-1].type == "budget_exhausted"
    assert events[-1].data["budget_type"] == "tool_calls"
