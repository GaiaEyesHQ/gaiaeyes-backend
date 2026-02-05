import os
from typing import Optional

from fastapi import Header, HTTPException, Request, status

from app.db import settings
from app.utils.auth import _normalize_uuid, decode_supabase_token


def _parse_tokens(s: Optional[str]) -> set[str]:
    if not s:
        return set()
    return {t.strip() for t in s.split(",") if t.strip()}


READ_TOKENS = _parse_tokens(os.getenv("READ_TOKENS", ""))
WRITE_TOKENS = _parse_tokens(os.getenv("WRITE_TOKENS", ""))

# Public GET allowlist (normalized, no trailing slash)
DEFAULT_PUBLIC_READ = [
    "/health",
    "/v1/space/visuals",
    "/v1/space/forecast/summary",
    "/v1/space/forecast/outlook",
    "/v1/local/check",
    "/v1/quakes/daily",
    "/v1/quakes/monthly",
    "/v1/earth/schumann/latest",
    "/v1/local/check",
    # diag endpoints are optional; uncomment if you want them public:
    # "/v1/space/visuals/diag",
]
PUBLIC_READ_ENABLED = os.getenv("PUBLIC_READ_ENABLED", "1").lower() in ("1", "true", "yes")
PUBLIC_READ_PATHS = [p.rstrip("/") for p in os.getenv("PUBLIC_READ_PATHS", "").split(",") if p.strip()] or DEFAULT_PUBLIC_READ


def _normalized(path: str) -> str:
    return path.rstrip("/") or "/"


def _is_public_read(request: Request) -> bool:
    if not PUBLIC_READ_ENABLED or request.method != "GET":
        return False
    path = _normalized(request.url.path)
    for p in PUBLIC_READ_PATHS:
        p = p.rstrip("/")
        if path == p or path.startswith(p + "/"):
            return True
    return False


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def _maybe_attach_dev_user(request: Request) -> None:
    """
    Attach a developer-scoped user to the request context when X-Dev-UserId is present.

    This is used for local/dev flows where we identify the "current user" via a header
    rather than a Supabase JWT. If the value cannot be normalized as a UUID, we still
    attach the trimmed raw value so downstream routes see a non-empty user_id.
    """
    raw = request.headers.get("X-Dev-UserId")
    if not raw:
        return
    normalized = _normalize_uuid(raw)
    request.state.user_id = normalized or raw.strip()


def _token_matches_dev(token: str) -> bool:
    return bool(settings.DEV_BEARER and token == settings.DEV_BEARER)


def _validate_supabase_token(request: Request, token: str) -> bool:
    user_id = decode_supabase_token(token)
    if user_id:
        request.state.user_id = user_id
        return True
    return False


def _is_allowed_read(request: Request, token: Optional[str]) -> bool:
    if not token:
        return False

    has_dev_header = bool(request.headers.get("X-Dev-UserId"))

    # If this is a known backend token (READ/WRITE) and a dev user header is present,
    # attach that user to the request context so user-scoped routes can work.
    if token in READ_TOKENS or token in WRITE_TOKENS:
        if has_dev_header or _token_matches_dev(token):
            _maybe_attach_dev_user(request)
        return True

    if _token_matches_dev(token):
        _maybe_attach_dev_user(request)
        return True

    return _validate_supabase_token(request, token)


def _is_allowed_write(request: Request, token: Optional[str]) -> bool:
    if not token:
        return False

    has_dev_header = bool(request.headers.get("X-Dev-UserId"))

    if token in WRITE_TOKENS:
        if has_dev_header or _token_matches_dev(token):
            _maybe_attach_dev_user(request)
        return True

    if _token_matches_dev(token):
        _maybe_attach_dev_user(request)
        return True

    return _validate_supabase_token(request, token)


async def require_read_auth(request: Request, authorization: Optional[str] = Header(None)):
    if _is_public_read(request):
        return
    token = _extract_bearer(authorization)
    if _is_allowed_read(request, token):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid Authorization header")


async def require_write_auth(request: Request, authorization: Optional[str] = Header(None)):
    token = _extract_bearer(authorization)
    if _is_allowed_write(request, token):
        # Ensure routes that depend on request.state.user_id still work
        if not getattr(request.state, "user_id", None) and token:
            user_id = decode_supabase_token(token)
            if user_id:
                request.state.user_id = user_id
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid Authorization header",
    )
