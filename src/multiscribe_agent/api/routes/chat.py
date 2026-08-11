"""Authenticated chat endpoints with optional SYSTEM_PASSWORD bypass for single-user mode."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_optional_user, is_admin_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.services.chat_service import ChatService

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _service(context: ServiceContext) -> ChatService:
    """Return the initialized chat service or surface a 503 to the caller."""
    if context.chat_service is None:
        raise HTTPException(status_code=503, detail="chat service unavailable")
    if not isinstance(context.chat_service, ChatService):
        raise HTTPException(status_code=503, detail="chat service unavailable")
    return context.chat_service


async def _require_user(
    context: ServiceContext,
    user: dict[str, object] | None,
) -> dict[str, object]:
    """Allow either a valid bearer token or the SYSTEM_PASSWORD bypass header."""
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="admin role required")
    return user


@router.post("/sessions")
async def create_session(
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
    user: dict[str, object] | None = Depends(get_optional_user),  # noqa: B008
) -> dict[str, object]:
    """Create a new chat session with an optional title."""
    await _require_user(context, user)
    title = str(payload.get("title", "") or "").strip()[:200]
    session = await _service(context).create_session(title)
    return _session_response(session)


@router.get("/sessions")
async def list_sessions(
    limit: int = 50,
    context: ServiceContext = Depends(get_context),  # noqa: B008
    user: dict[str, object] | None = Depends(get_optional_user),  # noqa: B008
) -> list[dict[str, object]]:
    """Return recent chat sessions in descending update order."""
    await _require_user(context, user)
    sessions = await _service(context).list_sessions(limit)
    return [_session_response(session) for session in sessions]


@router.get("/sessions/{session_id}/messages")
async def list_messages(
    session_id: str,
    limit: int = 200,
    context: ServiceContext = Depends(get_context),  # noqa: B008
    user: dict[str, object] | None = Depends(get_optional_user),  # noqa: B008
) -> list[dict[str, object]]:
    """Return chronological messages for a session."""
    await _require_user(context, user)
    service = _service(context)
    if await service.list_sessions(limit=1_000) and not any(
        session.id == session_id for session in await service.list_sessions(limit=1_000)
    ):
        raise HTTPException(status_code=404, detail="chat session not found")
    messages = await service.list_messages(session_id, limit)
    return [_message_response(message) for message in messages]


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
    user: dict[str, object] | None = Depends(get_optional_user),  # noqa: B008
) -> dict[str, object]:
    """Persist one user turn, run the agent, and persist the assistant reply."""
    await _require_user(context, user)
    content = str(payload.get("content", "") or "")
    if not content.strip():
        raise HTTPException(status_code=400, detail="content must not be empty")
    service = _service(context)
    reply = await service.send_message(session_id, content)
    if reply is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    return _message_response(reply)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    context: ServiceContext = Depends(get_context),  # noqa: B008
    user: dict[str, object] | None = Depends(get_optional_user),  # noqa: B008
) -> dict[str, str]:
    """Delete a chat session and cascade-remove its messages."""
    await _require_user(context, user)
    if not await _service(context).delete_session(session_id):
        raise HTTPException(status_code=404, detail="chat session not found")
    return {"status": "deleted"}


def _session_response(session) -> dict[str, object]:
    """Serialize a ChatSession without leaking internal metadata."""
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "message_count": session.message_count,
    }


def _message_response(message) -> dict[str, object]:
    """Serialize a ChatMessage into a JSON-friendly payload."""
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at,
    }
