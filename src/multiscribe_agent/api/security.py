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
    expires_at = datetime.now(UTC) + timedelta(hours=expires_hours)
    payload: dict[str, object] = {"sub": subject, "role": role, "exp": expires_at}
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
    """Resolve bearer or query-string authentication for protected API routes."""
    authorization = request.headers.get("Authorization", "")
    token = (
        authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
    )
    token = token or request.query_params.get("token", "")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    try:
        return decode_token(token, request.app.state.settings)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


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
