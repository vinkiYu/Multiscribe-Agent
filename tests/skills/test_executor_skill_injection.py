"""Regression test for executable skill instructions in agent prompts."""

from __future__ import annotations

from multiscribe_agent.agents.executor import AgentExecutor
from multiscribe_agent.agents.prompt_service import PromptService
from multiscribe_agent.domain.models import AgentDefinition, SkillEntry, SkillFrontmatter
from multiscribe_agent.skills.registry import get_skill_registry


def test_executor_injects_loaded_skill_summary() -> None:
    """A linked skill contributes name, description, and instruction content."""
    registry = get_skill_registry()
    registry.clear()
    registry.register(
        SkillEntry(
            id="weekly",
            name="Weekly Brief",
            description="A weekly report",
            instructions="Collect sources and summarize them.",
            is_builtin=True,
            frontmatter=SkillFrontmatter(name="Weekly Brief", description="A weekly report"),
        )
    )
    definition = AgentDefinition(
        id="agent",
        name="Agent",
        description="Test agent",
        system_prompt="Perform the task.",
        provider_id="provider",
        model="model",
        skill_ids=["weekly"],
    )
    executor = AgentExecutor(lambda _: None, None, PromptService())  # type: ignore[arg-type]
    prompt = executor._build_system_prompt(definition)
    assert "Weekly Brief" in prompt
    assert "Collect sources and summarize them." in prompt
