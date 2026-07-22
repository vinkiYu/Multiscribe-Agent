"""Tests for structured Harness context management."""

from multiscribe_agent.agents.context import HarnessContext
from multiscribe_agent.domain.models import ToolCall


def test_add_inject_and_build_messages() -> None:
    """Context builds system, injected, conversation, and tool messages in order."""
    context = HarnessContext("Base system")
    context.inject_memory("Remember the user preference.")
    context.inject_knowledge(["Fact one", "Fact two"])
    context.add_user("Question")
    context.add_assistant(
        "",
        [ToolCall(id="call-1", name="get_weather", arguments={"city": "Beijing"})],
    )
    context.add_tool_result("call-1", "get_weather", "sunny")

    messages = context.build_messages()

    assert [message.role for message in messages] == ["system", "user", "assistant", "tool"]
    assert "[Memory Data]" in messages[0].content
    assert "[Knowledge Data]" in messages[0].content
    assert messages[-1].tool_call_id == "call-1"


def test_trim_preserves_first_recent_and_tool_integrity() -> None:
    """A small budget removes middle history without splitting a tool exchange."""
    context = HarnessContext("system", token_budget=70)
    context.add_user("first-anchor")
    context.add_assistant("middle-" + "x" * 100)
    context.add_user("recent-question")
    context.add_assistant(
        "",
        [ToolCall(id="call-2", name="get_weather", arguments={"city": "Shanghai"})],
    )
    context.add_tool_result("call-2", "get_weather", "recent-tool-result")

    messages = context.build_messages()
    contents = [message.content for message in messages]

    assert "first-anchor" in contents
    assert not any(content.startswith("middle-") for content in contents)
    assert messages[-2].role == "assistant"
    assert messages[-1].role == "tool"
    assert messages[-1].tool_call_id == messages[-2].tool_calls[0].id


def test_tool_result_compression_keeps_head_tail_and_marker() -> None:
    """Oversized tool output retains diagnostic context at both ends."""
    context = HarnessContext("system", tool_result_limit=160)
    context.add_tool_result("call-3", "large_tool", "important-head" + "a" * 300 + "important-tail")

    result = context.build_messages()[-1].content

    assert result.startswith("important-head")
    assert "[tool result truncated: original_chars=328; omitted_chars=" in result
    assert result.endswith("important-tail")
    assert len(result) <= 160


def test_tool_result_compression_degrades_for_tiny_limit() -> None:
    """A tiny result budget remains bounded even when the full marker cannot fit."""
    context = HarnessContext("system", tool_result_limit=8)
    context.add_tool_result("call-4", "large_tool", "x" * 100)

    result = context.build_messages()[-1].content

    assert result == "[truncat"


def test_trim_retains_important_message_and_summarizes_discarded_history() -> None:
    """Middle history becomes a checkpoint while explicit constraints remain verbatim."""
    context = HarnessContext("system", token_budget=600)
    context.add_user("initial task")
    context.add_assistant("discarded conclusion " + "x" * 1_600)
    context.add_user("never include financing news", important=True)
    context.add_assistant("recent answer " + "y" * 1_000)

    messages = context.build_messages()
    contents = [message.content for message in messages]

    assert "never include financing news" in contents
    assert "[Conversation Summary]" in messages[0].content
    assert "Assistant conclusion: discarded conclusion" in messages[0].content


def test_token_estimate_is_monotonic_and_usage_accumulates() -> None:
    """Longer context estimates more tokens and usage accounting is cumulative."""
    context = HarnessContext("system")
    initial = context.estimate_tokens()
    context.add_user("x" * 100)
    after_user = context.estimate_tokens()

    assert after_user > initial
    assert context.usage_summary.total_tokens == 0
