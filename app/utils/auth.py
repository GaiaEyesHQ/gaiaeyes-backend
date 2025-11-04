from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

import jwt
from fastapi import HTTPException, Request, status

from .. import db

logger = logging.getLogger(__name__)


def _normalize_uuid(value: str | None) -> Optional[str]:
    if not value:
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def decode_supabase_token(token: str) -> Optional[str]:
    """Return the user_id encoded in a Supabase JWT if validation succeeds."""
    secret = db.settings.SUPABASE_JWT_SECRET
    if not secret:
        return None
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.InvalidTokenError as exc:
        logger.debug("Supabase JWT validation failed: %s", exc)
        return None

    sub = payload.get("sub") or payload.get("user_id")
    if isinstance(sub, str):
        return _normalize_uuid(sub)
    return None


async def require_auth(request: Request) -> None:
    """FastAPI dependency that validates a bearer token and attaches request.state.user_id."""

    auth_header = request.headers.get("Authorization", "") or ""
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

    settings = db.settings

    # Developer token path: attach optional X-Dev-UserId when present
    if settings.DEV_BEARER and token == settings.DEV_BEARER:
        request.state.user_id = _normalize_uuid(request.headers.get("X-Dev-UserId"))
        return

    user_id = decode_supabase_token(token)
    if user_id:
        request.state.user_id = user_id
        return

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")


async def require_admin(request: Request) -> None:
    """Ensure the caller presents the developer bearer token."""

    auth_header = request.headers.get("Authorization", "") or ""
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin token required")

    token = auth_header.split(" ", 1)[1].strip()
    settings = db.settings
    if settings.DEV_BEARER and token == settings.DEV_BEARER:
        return

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin token required")
