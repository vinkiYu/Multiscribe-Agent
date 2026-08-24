"""Conversation service that persists user/assistant turns and runs async preference extraction."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Protocol

import structlog

from multiscribe_agent.core.errors import ProviderError
from multiscribe_agent.domain.models import AgentDefinition, AIMessage, ChatMessage, ChatSession
from multiscribe_agent.memory.chat_sessions import ChatSessionRepository
from multiscribe_agent.memory.extractor import PreferenceExtractor
from multiscribe_agent.memory.preference_store import PreferenceStore, UserPreferences

log = structlog.get_logger(__name__)

_UNBOUND_PLACEHOLDER = (
    "\uff08\u5f53\u524d\u672a\u914d\u7f6e\u5bf9\u8bdd"
    " Agent\uff1b\u8bb0\u5f55\u5df2\u4fdd\u5b58\u3002\uff09"
)
_RUNNER_UNAVAILABLE_MESSAGE = (
    "\u5bf9\u8bdd Agent \u6682\u65f6\u4e0d\u53ef\u7528\uff0c"
    "\u5df2\u8bb0\u5f55\u4f60\u7684\u8f93\u5165\u3002"
)


class ChatAgentRunner(Protocol):
    """Minimal contract that wraps AgentExecutor.run_result for the chat surface."""

    async def run(self, agent_def: AgentDefinition, user_input: str) -> str:
        """Execute one agent definition and return its content text."""

    async def stream(self, agent_def: AgentDefinition, user_input: str) -> object:
        """Yield AgentEvent-like objects for one agent turn; absent on legacy runners."""

        def _empty() -> None:
            return None

        _empty()  # pragma: no cover - keeps ruff happy with the no-self-use stub
        yield None  # protocol marker; consumers use the runner's own stream when present


class ChatService:
    """Persist chat sessions, run one agent turn, and dispatch async preference extraction."""

    def __init__(
        self,
        sessions: ChatSessionRepository,
        preference_store: PreferenceStore,
        extractor: PreferenceExtractor | None,
        agent_runner: ChatAgentRunner | None = None,
        agent_def: AgentDefinition | None = None,
    ) -> None:
        """Bind the persistence, preference, and agent dependencies."""
        self._sessions = sessions
        self._preference_store = preference_store
        self._extractor = extractor
        self._agent_runner = agent_runner
        self._agent_def = agent_def

    def bind_agent(self, runner: ChatAgentRunner, agent_def: AgentDefinition) -> None:
        """Late-bind the agent runner and definition after bootstrap built the executor."""
        self._agent_runner = runner
        self._agent_def = agent_def

    async def create_session(self, title: str = "") -> ChatSession:
        """Create a new empty chat session."""
        return await self._sessions.create_session(title)

    async def list_sessions(self, limit: int = 50) -> list[ChatSession]:
        """Return recent sessions ordered by last activity."""
        return list(await self._sessions.list_sessions(limit))

    async def list_messages(self, session_id: str, limit: int = 200) -> list[ChatMessage]:
        """Return chronological messages for a session."""
        return list(await self._sessions.list_messages(session_id, limit))

    async def delete_session(self, session_id: str) -> bool:
        """Remove one session and its messages."""
        return await self._sessions.delete_session(session_id)

    async def send_message(
        self,
        session_id: str,
        content: str,
    ) -> ChatMessage | None:
        """Persist one user turn, run the agent, persist the reply, schedule extraction."""
        if not content or not content.strip():
            raise ValueError("message content must not be empty")
        user_message = await self._sessions.append_message(session_id, "user", content)
        if user_message is None:
            return None
        await self._maybe_autotitle(session_id, content)
        reply_text = await self._run_agent(content)
        assistant_message = await self._sessions.append_message(session_id, "assistant", reply_text)
        self._defer_preference_extraction(session_id)
        return assistant_message

    async def stream_message(
        self, session_id: str, content: str
    ) -> AsyncIterator[dict[str, object]]:
        """Yield typed events while a chat turn streams, then persist the assistant reply."""
        if not content or not content.strip():
            raise ValueError("message content must not be empty")
        if self._agent_runner is None or self._agent_def is None:
            yield {"type": "error", "message": _UNBOUND_PLACEHOLDER}
            return

        user_message = await self._sessions.append_message(session_id, "user", content)
        if user_message is None:
            yield {"type": "error", "message": "chat session not found"}
            return
        await self._maybe_autotitle(session_id, content)
        yield {"type": "user_persisted", "message": user_message}

        try:
            stream_method = getattr(self._agent_runner, "stream", None)
            if stream_method is None:
                reply_text = await self._run_agent(content)
                assistant_message = await self._sessions.append_message(
                    session_id, "assistant", reply_text
                )
                yield {"type": "assistant_persisted", "message": assistant_message}
                self._defer_preference_extraction(session_id)
                return

            content_parts: list[str] = []

            def _data_text(event: object, key: str) -> str:
                data = getattr(event, "data", None)
                if not isinstance(data, Mapping):
                    return ""
                value = data.get(key, "")
                return str(value) if value else ""

            async for event in stream_method(self._agent_def, content):
                event_type = getattr(event, "type", None)
                if event_type == "content":
                    text = _data_text(event, "content")
                    if text:
                        content_parts.append(text)
                        yield {"type": "content", "delta": text}
                elif event_type == "final_content":
                    text = _data_text(event, "content")
                    if text:
                        # final_content is the canonical full text; if the
                        # stream's last delta already equals it we keep the
                        # list unchanged so the join doesn't duplicate it.
                        if content_parts and content_parts[-1] == text:
                            pass
                        else:
                            content_parts.append(text)
                elif event_type == "error":
                    yield {"type": "error", "message": _RUNNER_UNAVAILABLE_MESSAGE}
                    return

            final_text = "".join(content_parts).strip() or _RUNNER_UNAVAILABLE_MESSAGE
            assistant_message = await self._sessions.append_message(
                session_id, "assistant", final_text
            )
            yield {"type": "assistant_persisted", "message": assistant_message}
            self._defer_preference_extraction(session_id)
        except (RuntimeError, ValueError, OSError, ProviderError) as exc:  # pragma: no cover
            log.warning("chat_agent_stream_failed", error_type=type(exc).__name__)
            yield {"type": "error", "message": _RUNNER_UNAVAILABLE_MESSAGE}

    async def _maybe_autotitle(self, session_id: str, content: str) -> None:
        """Derive a session title from the first user message when the slot is empty."""
        session = await self._sessions.get_session(session_id)
        if session is None or session.title.strip():
            return
        compact = " ".join(content.split())
        if not compact:
            return
        title = compact[:24] + ("…" if len(compact) > 24 else "")
        await self._update_session_title(session_id, title)

    async def _update_session_title(self, session_id: str, title: str) -> None:
        """Persist a new title without disturbing the message counters."""
        try:
            await self._sessions.update_title(session_id, title)
        except (OSError, RuntimeError, ValueError) as exc:  # pragma: no cover
            log.warning(
                "chat_session_autotitle_failed",
                error_type=type(exc).__name__,
            )

    async def _run_agent(self, user_input: str) -> str:
        """Run the configured agent runner or return a no-op placeholder."""
        if self._agent_runner is None or self._agent_def is None:
            return _UNBOUND_PLACEHOLDER
        try:
            return await self._agent_runner.run(self._agent_def, user_input)
        except (RuntimeError, ValueError, OSError, ProviderError) as exc:  # pragma: no cover
            log.warning("chat_agent_run_failed", error_type=type(exc).__name__)
            return _RUNNER_UNAVAILABLE_MESSAGE

    def _defer_preference_extraction(self, session_id: str) -> None:
        """Schedule preference extraction; failures stay invisible to the chat caller."""
        if self._extractor is None:
            return
        extractor = self._extractor

        async def runner() -> None:
            try:
                history = await self._sessions.list_messages(session_id, limit=20)
                if not history:
                    return
                messages = [
                    AIMessage(role=message.role, content=message.content) for message in history
                ]
                delta = await extractor.extract_from_conversation(messages)
                if not delta:
                    return
                current = await self._preference_store.load()
                updated = extractor.merge_into(current, delta)
                if updated != current:
                    await self._preference_store.save(updated)
            except (OSError, RuntimeError, ValueError) as exc:  # pragma: no cover
                log.warning(
                    "chat_preference_extraction_failed",
                    error_type=type(exc).__name__,
                )

        try:
            loop = asyncio.get_running_loop()
            _task = loop.create_task(runner())
            del _task
        except RuntimeError:  # pragma: no cover
            log.info("chat_preference_extraction_skipped_no_loop")


def ensure_messages(messages: Sequence[ChatMessage]) -> list[AIMessage]:
    """Convert persisted chat messages into provider-shaped AIMessage values."""
    return [AIMessage(role=message.role, content=message.content) for message in messages]


def preference_diff(before: UserPreferences, after: UserPreferences) -> dict[str, object]:
    """Return the keys that differ between two preference objects."""
    diff: dict[str, object] = {}
    for field in ("preferred_tags", "block_sources", "blocked_topics"):
        if getattr(before, field) != getattr(after, field):
            diff[field] = list(getattr(after, field))
    if before.push_time != after.push_time:
        diff["push_time"] = after.push_time
    if before.importance_threshold != after.importance_threshold:
        diff["importance_threshold"] = after.importance_threshold
    return diff
