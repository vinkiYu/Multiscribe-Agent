"""Tests for shared domain data contracts."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from multiscribe_agent.domain.models import (
    AgentDefinition,
    AIMessage,
    AIResponse,
    CommitRecord,
    KBCategory,
    KBChunk,
    KBDocument,
    MCPConfig,
    MemoryEntry,
    ScheduleTask,
    SkillEntry,
    SkillFrontmatter,
    SourceData,
    TaskLog,
    TokenUsage,
    ToolCall,
    ToolDefinition,
    UnifiedData,
    WorkflowDefinition,
    WorkflowStep,
)


def _unified_data_fields() -> dict[str, object]:
    return {
        "id": "item-1",
        "title": "A useful article",
        "url": "https://example.com/article",
        "description": "Summary",
        "published_date": "2026-07-15T08:00:00Z",
        "source": "Example",
        "category": "news",
    }


def test_unified_data_constructs() -> None:
    """Unified content retains its required and extensible fields."""
    item = UnifiedData(**_unified_data_fields(), metadata={"ai_score": 90})

    assert item.id == "item-1"
    assert item.metadata["ai_score"] == 90


def test_ai_message_and_response_construct() -> None:
    """AI contracts support tool calls and token usage."""
    call = ToolCall(id="call-1", name="search", arguments={"query": "agents"})
    message = AIMessage(role="assistant", content="Searching", tool_calls=[call])
    response = AIResponse(
        content="Done",
        tool_calls=[call],
        usage=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        raw={"provider": "test"},
    )

    assert message.tool_calls == [call]
    assert response.usage is not None
    assert response.usage.total_tokens == 15


def test_agent_workflow_and_tool_construct() -> None:
    """Agent, workflow, and tool definitions compose through identifiers."""
    agent = AgentDefinition(
        id="agent-1",
        name="Curator",
        description="Ranks content",
        system_prompt="Rank the supplied items.",
        provider_id="default-openai",
        model="gpt-test",
    )
    step = WorkflowStep(
        id="step-1",
        name="Curate",
        step_type="agent",
        agent_id=agent.id,
        max_iterations=2,
        exit_condition="score >= 80",
    )
    workflow = WorkflowDefinition(
        id="workflow-1",
        name="Daily digest",
        description="Curates a digest",
        steps=[step],
    )
    tool = ToolDefinition(id="tool-1", name="search", description="Search content")

    assert workflow.steps[0].agent_id == agent.id
    assert tool.parameters == {}


def test_mcp_and_skill_construct() -> None:
    """MCP and skill contracts preserve executable metadata."""
    mcp = MCPConfig(id="mcp-1", name="Local tools", transport="stdio", command="server")
    frontmatter = SkillFrontmatter(name="summarize", description="Summarize text")
    skill = SkillEntry(
        id="skill-1",
        name="Summarize",
        description="Summarizes source content",
        instructions="Return a concise summary.",
        is_builtin=True,
        frontmatter=frontmatter,
    )

    assert mcp.args == []
    assert skill.frontmatter.name == "summarize"


def test_persistence_models_construct() -> None:
    """Persistence-facing entities expose the fields needed by P2."""
    source = SourceData(
        **_unified_data_fields(),
        fetched_at="2026-07-15T09:00:00Z",
        ingestion_date="2026-07-15",
        adapter_name="rss-adapter",
    )
    task_log = TaskLog(
        task_id="task-1",
        task_name="Daily ingest",
        start_time="2026-07-15T09:00:00Z",
        status="running",
    )
    commit = CommitRecord(
        date="2026-07-15",
        platform="github",
        file_path="daily/2026-07-15.md",
        commit_message="Publish daily digest",
        commit_time="2026-07-15T10:00:00Z",
        full_content="# Digest",
    )
    schedule = ScheduleTask(
        id="schedule-1",
        name="Daily digest",
        task_type="daily_digest",
        cron="0 9 * * *",
    )

    assert source.adapter_name == "rss-adapter"
    assert task_log.status == "running"
    assert commit.platform == "github"
    assert schedule.enabled is True


def test_memory_and_knowledge_models_construct() -> None:
    """Future memory and knowledge services have stable placeholder contracts."""
    memory = MemoryEntry(
        id="memory-1",
        agent_id="agent-1",
        content="The user prefers concise summaries.",
        importance=4,
        tags=["preference"],
        created_at=1_752_566_400,
    )
    category = KBCategory(
        id="category-1",
        name="Architecture",
        description="Architecture documents",
        document_count=1,
        last_updated_at=1_752_566_400,
    )
    document = KBDocument(
        id="document-1",
        category_id=category.id,
        name="Architecture",
        file_name="ARCHITECTURE.md",
        type="md",
        summary="System architecture",
        chunk_count=1,
        created_at=1_752_566_400,
        updated_at=1_752_566_400,
    )
    chunk = KBChunk(
        id="chunk-1",
        document_id=document.id,
        content="The domain layer is the dependency root.",
        index=0,
    )

    assert memory.tags == ["preference"]
    assert category.document_count == 1
    assert document.category_id == category.id
    assert chunk.document_id == document.id


@pytest.mark.parametrize("missing_field", ["id", "published_date"])
def test_unified_data_requires_identity_and_publication_date(missing_field: str) -> None:
    """UnifiedData rejects either missing required identity field."""
    fields = _unified_data_fields()
    del fields[missing_field]

    with pytest.raises(PydanticValidationError):
        UnifiedData(**fields)


@pytest.mark.parametrize("field", ["id", "published_date"])
def test_unified_data_rejects_blank_identity_fields(field: str) -> None:
    """UnifiedData rejects blank identifiers and publication dates."""
    fields = _unified_data_fields()
    fields[field] = "   "

    with pytest.raises(PydanticValidationError):
        UnifiedData(**fields)


def test_ai_message_rejects_unknown_role() -> None:
    """AIMessage accepts only the provider-neutral role vocabulary."""
    with pytest.raises(PydanticValidationError):
        AIMessage(role="operator", content="invalid")


def test_workflow_step_rejects_unknown_type() -> None:
    """WorkflowStep accepts only agent or nested-workflow nodes."""
    with pytest.raises(PydanticValidationError):
        WorkflowStep(id="step-1", name="Invalid", step_type="script")


def test_mutable_defaults_are_isolated() -> None:
    """Mutable model defaults are not shared between instances."""
    first = ToolDefinition(id="tool-1", name="one", description="First")
    second = ToolDefinition(id="tool-2", name="two", description="Second")

    first.parameters["type"] = "object"

    assert second.parameters == {}
