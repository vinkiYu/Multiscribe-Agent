"""Tests for PromptService, Planner, and Reflector basics."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FakeProvider

from multiscribe_agent.agents.planner import Planner
from multiscribe_agent.agents.prompt_service import PromptService
from multiscribe_agent.agents.reflector import Reflector
from multiscribe_agent.domain.models import AIResponse


@pytest.mark.asyncio
async def test_planner_returns_json_steps() -> None:
    """Planner parses a provider JSON array into ordered non-empty steps."""
    provider = FakeProvider(generated_responses=[AIResponse(content='["Research", "Draft"]')])

    steps = await Planner().plan("Write a report", provider)

    assert steps == ["Research", "Draft"]


@pytest.mark.asyncio
async def test_reflector_returns_structured_score_and_retry() -> None:
    """Reflector derives should_retry from a validated fail assessment."""
    provider = FakeProvider(
        generated_responses=[
            AIResponse(content='{"quality":"fail","score":0.4,"feedback":"Add sources"}')
        ]
    )

    reflection = await Reflector().assess("Write", "Draft", provider)

    assert reflection.quality == "fail"
    assert reflection.score == 0.4
    assert reflection.feedback == "Add sources"
    assert reflection.should_retry is True


def test_prompt_service_loads_sections_and_renders_variables(tmp_path: Path) -> None:
    """Prompt sections load independently and render with strict Jinja variables."""
    template = tmp_path / "sample.md"
    template.write_text(
        "## [First]\nHello {{ name }}\n\n## [Second]\nGoodbye",
        encoding="utf-8",
    )
    service = PromptService(tmp_path)

    assert service.get_section("sample", "Second") == "Goodbye"
    assert service.render("sample", "First", name="Codex") == "Hello Codex"

    with pytest.raises(KeyError, match="prompt section not found"):
        service.get_section("sample", "Missing")
