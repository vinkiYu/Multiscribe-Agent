"""Structured context-window management for Agent Harness runs."""

from __future__ import annotations

import json

from multiscribe_agent.domain.models import AIMessage, TokenUsage, ToolCall

DEFAULT_TOKEN_BUDGET = 120_000
TOOL_RESULT_LIMIT = 8_000
TOOL_RESULT_TAIL = 6_000
MESSAGE_OVERHEAD_TOKENS = 4
USER_MESSAGE_BUDGET_RATIO = 0.8


class HarnessContext:
    """Manage structured messages, injected context, trimming, and token usage."""

    def __init__(
        self,
        system_prompt: str,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
        *,
        tool_result_limit: int = TOOL_RESULT_LIMIT,
    ) -> None:
        """Create an empty context with a fixed token budget.

        Args:
            system_prompt: Base instructions supplied by the agent definition.
            token_budget: Approximate maximum tokens passed to the provider.
            tool_result_limit: Character threshold before tool output compression.

        Raises:
            ValueError: If a configured limit is not positive.
        """
        if token_budget <= 0:
            raise ValueError("token_budget must be positive")
        if tool_result_limit <= 0:
            raise ValueError("tool_result_limit must be positive")
        self.system_prompt = system_prompt
        self.token_budget = token_budget
        self.tool_result_limit = tool_result_limit
        self.messages: list[AIMessage] = []
        self._memory: list[str] = []
        self._knowledge: list[str] = []
        self._usage = TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0)

    def add_user(self, message: str) -> None:
        """Append a user message and trim the context when necessary."""
        self.messages.append(
            AIMessage(role="user", content=self._maybe_truncate_user_message(message))
        )
        self.trim_if_needed()

    def add_assistant(self, message: str, tool_calls: list[ToolCall] | None = None) -> None:
        """Append an assistant message, including any requested tool calls."""
        self.messages.append(
            AIMessage(role="assistant", content=message, tool_calls=tool_calls or None)
        )
        self.trim_if_needed()

    def add_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        """Append a tool result after compressing oversized content."""
        self.messages.append(
            AIMessage(
                role="tool",
                content=self._compress_tool_result(content),
                tool_call_id=tool_call_id,
                name=name,
            )
        )
        self.trim_if_needed()

    def inject_memory(self, summary: str) -> None:
        """Inject a future memory-service summary into the system context."""
        if summary.strip():
            self._memory.append(summary.strip())

    def inject_knowledge(self, snippets: list[str]) -> None:
        """Inject future knowledge-service snippets into the system context."""
        self._knowledge.extend(snippet.strip() for snippet in snippets if snippet.strip())

    def add_usage(self, usage: TokenUsage | None) -> None:
        """Accumulate provider token usage for the current run."""
        if usage is None:
            return
        self._usage = TokenUsage(
            input_tokens=self._usage.input_tokens + usage.input_tokens,
            output_tokens=self._usage.output_tokens + usage.output_tokens,
            total_tokens=self._usage.total_tokens + usage.total_tokens,
        )

    @property
    def usage_summary(self) -> TokenUsage:
        """Return a copy of cumulative provider token usage."""
        return self._usage.model_copy()

    def estimate_tokens(self, messages: list[AIMessage] | None = None) -> int:
        """Estimate message tokens monotonically using a four-characters heuristic."""
        selected = self.build_messages(trim=False) if messages is None else messages
        return sum(self._estimate_message(message) for message in selected)

    def should_warn_budget(self, threshold: float = USER_MESSAGE_BUDGET_RATIO) -> bool:
        """Return whether the untrimmed context has reached a budget threshold."""
        if self.token_budget <= 0:
            return False
        return self.estimate_tokens(self.build_messages(trim=False)) >= int(
            self.token_budget * threshold
        )

    def estimated_tokens_remaining(self) -> int:
        """Return the approximate number of tokens available before the budget is hit."""
        current = self.estimate_tokens(self.build_messages(trim=False))
        return max(0, self.token_budget - current)

    def trim_if_needed(self) -> None:
        """Trim middle history while preserving the first and recent atomic groups."""
        if self.estimate_tokens(self.build_messages(trim=False)) <= self.token_budget:
            return

        groups = self._message_groups()
        if len(groups) <= 2:
            return

        system_tokens = self._estimate_message(self._system_message())
        first = groups[0]
        selected_tail: list[list[AIMessage]] = []
        used = system_tokens + self._estimate_group(first)
        for group in reversed(groups[1:]):
            group_tokens = self._estimate_group(group)
            if selected_tail and used + group_tokens > self.token_budget:
                break
            selected_tail.append(group)
            used += group_tokens
            if used >= self.token_budget:
                break

        if not selected_tail:
            selected_tail.append(groups[-1])
        recent_messages = [message for group in reversed(selected_tail) for message in group]
        self.messages = [*first, *recent_messages]

    def build_messages(self, *, trim: bool = True) -> list[AIMessage]:
        """Build provider-ready messages with one structured system message."""
        if trim:
            self.trim_if_needed()
        copied_messages = [message.model_copy(deep=True) for message in self.messages]
        return [self._system_message(), *copied_messages]

    def _system_message(self) -> AIMessage:
        sections = [self.system_prompt.strip()]
        if self._memory:
            sections.append("[Memory]\n" + "\n\n".join(self._memory))
        if self._knowledge:
            sections.append("[Knowledge]\n" + "\n".join(f"- {item}" for item in self._knowledge))
        content = "\n\n".join(section for section in sections if section)
        return AIMessage(role="system", content=content)

    def _message_groups(self) -> list[list[AIMessage]]:
        groups: list[list[AIMessage]] = []
        index = 0
        while index < len(self.messages):
            message = self.messages[index]
            group = [message]
            if message.role == "assistant" and message.tool_calls:
                call_ids = {tool_call.id for tool_call in message.tool_calls}
                next_index = index + 1
                while next_index < len(self.messages):
                    candidate = self.messages[next_index]
                    if candidate.role != "tool" or candidate.tool_call_id not in call_ids:
                        break
                    group.append(candidate)
                    next_index += 1
                index = next_index
            else:
                index += 1
            groups.append(group)
        return groups

    def _compress_tool_result(self, content: str) -> str:
        if len(content) <= self.tool_result_limit:
            return content
        tail_length = min(TOOL_RESULT_TAIL, self.tool_result_limit)
        marker = f"[tool result truncated: original_chars={len(content)}]\n"
        return marker + content[-tail_length:]

    def _maybe_truncate_user_message(self, message: str) -> str:
        """Keep one user message within the share of the budget reserved for it."""
        estimated = self._estimate_text(message)
        threshold = max(1, int(self.token_budget * USER_MESSAGE_BUDGET_RATIO))
        if estimated <= threshold:
            return message

        marker = f"[Truncated]\n[original_tokens={estimated}; message_budget={threshold}]"
        char_limit = max(len(marker) + 2, threshold * 4)
        remaining = max(0, char_limit - len(marker) - 2)
        head_length = remaining // 2
        tail_length = remaining - head_length
        head = message[:head_length]
        tail = message[-tail_length:] if tail_length else ""
        return f"{head}\n{marker}\n{tail}"

    @staticmethod
    def _estimate_group(group: list[AIMessage]) -> int:
        return sum(HarnessContext._estimate_message(message) for message in group)

    @staticmethod
    def _estimate_message(message: AIMessage) -> int:
        estimate = HarnessContext._estimate_text(message.content)
        if message.tool_calls:
            tool_payload = json.dumps(
                [tool_call.model_dump(mode="json") for tool_call in message.tool_calls],
                ensure_ascii=False,
            )
            estimate += (len(tool_payload) + 3) // 4
        return max(1, estimate)

    @staticmethod
    def _estimate_text(text: str) -> int:
        """Estimate tokens for raw text using the four-characters heuristic."""
        return (len(text) + MESSAGE_OVERHEAD_TOKENS + 3) // 4
