"""Regression tests for HarnessContext overflow protection and budget warnings."""

import pytest

from multiscribe_agent.agents.context import ContextBudgetError, HarnessContext
from multiscribe_agent.domain.models import ToolCall


def test_oversized_user_message_is_truncated_before_provider_input() -> None:
    """A single oversized message is bounded and carries an explicit marker."""
    context = HarnessContext("system", token_budget=100)
    original = "head-" + ("x" * 2_000) + "-tail"

    context.add_user(original)

    message = context.messages[-1].content
    assert "[Truncated]" in message
    assert len(message) < len(original)
    assert message.startswith("head-")
    assert message.endswith("-tail")
    assert context.estimate_tokens(context.build_messages(trim=False)) <= context.token_budget


def test_user_message_under_budget_is_preserved() -> None:
    """Normal-sized user input is not rewritten."""
    context = HarnessContext("system", token_budget=100)

    context.add_user("short question")

    assert context.messages[-1].content == "short question"


def test_should_warn_budget_uses_untrimmed_context() -> None:
    """The warning reflects the current context before history trimming."""
    context = HarnessContext("system", token_budget=100)
    context.add_user("x" * 320)

    assert context.should_warn_budget()
    assert context.estimated_tokens_remaining() < context.token_budget


def test_should_warn_budget_can_use_a_custom_threshold() -> None:
    """Callers can choose a lower warning threshold for provider-specific budgets."""
    context = HarnessContext("system", token_budget=100)
    context.add_user("x" * 200)

    assert context.should_warn_budget(0.5)


def test_protected_tool_exchange_fails_instead_of_sending_hidden_overflow() -> None:
    """Safety/current-goal content is never silently removed to make an invalid request fit."""
    context = HarnessContext("system", token_budget=35)
    context.add_user("current goal", important=True)
    context.add_assistant(
        "",
        [ToolCall(id="call", name="large_schema_tool", arguments={"value": "x" * 80})],
        important=True,
    )
    context.add_tool_result("call", "large_schema_tool", "evidence", important=True)

    with pytest.raises(ContextBudgetError, match="context_budget_unresolvable"):
        context.build_messages()
