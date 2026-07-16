"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from multiscribe_agent.api.security import create_access_token, verify_login_password

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    """Password credentials accepted by the local MVP login endpoint."""

    password: str


@router.post("/api/login")
async def login(payload: LoginRequest, request: Request) -> dict[str, object]:
    """Validate the local password and issue a short-lived administrator token."""
    settings = request.app.state.settings
    if not verify_login_password(payload.password, settings):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    token = create_access_token("admin", "admin", 24, settings)
    return {
        "access_token": token,
        "token_type": "bearer",
        "must_change_password": not bool(settings.system_password),
    }
