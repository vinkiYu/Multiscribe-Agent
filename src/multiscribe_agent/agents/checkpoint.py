"""Deterministic structured checkpoints for compacted conversations."""

from __future__ import annotations

from dataclasses import dataclass, field

from multiscribe_agent.domain.models import AIMessage


@dataclass(slots=True)
class ConversationCheckpoint:
    current_goal: str = ""
    hard_constraints: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    completed_actions: list[str] = field(default_factory=list)
    key_evidence: list[str] = field(default_factory=list)
    open_items: list[str] = field(default_factory=list)
    failed_attempts: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)

    @classmethod
    def from_groups(cls, groups: list[list[AIMessage]]) -> ConversationCheckpoint:
        checkpoint = cls()
        for group in groups:
            first = group[0]
            excerpt = " ".join(first.content.split())[:240]
            if first.role == "user":
                checkpoint.current_goal = excerpt
                checkpoint.hard_constraints.append(excerpt)
                checkpoint.open_items.append(excerpt)
            elif first.role == "assistant" and first.tool_calls:
                checkpoint.completed_actions.extend(call.name for call in first.tool_calls)
                checkpoint.key_evidence.extend(
                    f"{item.name or 'tool'}: {' '.join(item.content.split())[:240]}"
                    for item in group[1:]
                )
            elif first.role == "assistant":
                checkpoint.decisions.append(excerpt)
        return checkpoint

    def render(self) -> str:
        sections: list[str] = []
        for title, value in (
            ("Current goal", [self.current_goal] if self.current_goal else []),
            ("Hard constraints", self.hard_constraints),
            ("Assistant conclusion", self.decisions),
            ("Completed actions", self.completed_actions),
            ("Key evidence", self.key_evidence),
            ("Open items", self.open_items),
            ("Failed attempts", self.failed_attempts),
            ("Next actions", self.next_actions),
        ):
            if value:
                first, *remaining = value
                rendered = f"{title}: {first}"
                if remaining:
                    rendered += "\n" + "\n".join(f"- {item}" for item in remaining)
                sections.append(rendered)
        return "\n".join(sections)
