"""JWT authentication helpers and FastAPI user dependency."""

from __future__ import annotations

import hmac
import os
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from jose import JWTError, jwt  # type: ignore[import-untyped]

from multiscribe_agent.config import SystemSettings
from multiscribe_agent.core.errors import AuthError
from multiscribe_agent.core.logging import get_logger

ALGORITHM = "HS256"
DEVELOPMENT_SECRET = "multiscribe-development-jwt-secret"  # noqa: S105


def create_access_token(
    subject: str, role: str, expires_hours: int, settings: SystemSettings
) -> str:
    """Create a signed bearer token, using a development fallback only outside production."""
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(hours=expires_hours)
    payload: dict[str, object] = {
        "sub": subject,
        "role": role,
        "iat": issued_at,
        "exp": expires_at,
    }
    if not settings.system_password:
        payload["must_change_password"] = True
    return str(jwt.encode(payload, _secret(settings), algorithm=ALGORITHM))


def decode_token(token: str, settings: SystemSettings) -> dict[str, object]:
    """Decode one JWT or raise the domain authentication error."""
    try:
        decoded = jwt.decode(token, _secret(settings), algorithms=[ALGORITHM])
    except JWTError as exc:
        raise AuthError("invalid or expired access token") from exc
    return dict(decoded)


async def get_current_user(request: Request) -> dict[str, object]:
    """Resolve bearer authentication for protected API routes."""
    authorization = request.headers.get("Authorization", "")
    token = (
        authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    try:
        return decode_token(token, request.app.state.settings)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


async def get_optional_user(request: Request) -> dict[str, object] | None:
    """Resolve bearer authentication, returning None on absence or invalid token.

    Used by routes that allow a SYSTEM_PASSWORD downgrade path: when no system
    password is configured, the ``X-Admin-Bypass: 1`` header can replace bearer
    auth so a single-user deployment can use the UI without first setting a
    password.
    """
    settings = request.app.state.settings
    configured_password = bool(getattr(settings, "system_password", ""))
    if not configured_password and request.headers.get("X-Admin-Bypass", "").strip() == "1":
        return {"sub": "admin", "role": "admin", "must_change_password": True}
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return None
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


def is_admin_user(user: dict[str, object] | None) -> bool:
    """Return whether the optional-auth user dict looks like a local admin."""
    if not user:
        return False
    subject = user.get("sub")
    role = user.get("role")
    return subject == "admin" or role == "admin"


def verify_login_password(password: str, settings: SystemSettings) -> bool:
    """Compare login input with configured or explicitly documented development password."""
    expected = settings.system_password or "admin123"
    return hmac.compare_digest(password, expected)


def _secret(settings: SystemSettings) -> str:
    """Resolve the configured JWT secret without allowing a production fallback."""
    if settings.jwt_secret:
        return settings.jwt_secret
    if os.getenv("MULTISCRIBE_ENV", "development").casefold() == "production":
        raise AuthError("jwt_secret must be configured in production")
    get_logger().warning("jwt_development_secret_fallback")
    return DEVELOPMENT_SECRET
