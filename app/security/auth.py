import os
from typing import Optional

from fastapi import Header, HTTPException, Request, status


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
    "/v1/quakes/daily",
    "/v1/quakes/monthly",
    "/v1/earth/schumann/latest",
    "/v1/space/series",
    "/v1/series",
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


async def require_read_auth(request: Request, authorization: Optional[str] = Header(None)):
    if _is_public_read(request):
        return
    token = _extract_bearer(authorization)
    if token and (token in READ_TOKENS or token in WRITE_TOKENS):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid Authorization header")


async def require_write_auth(authorization: Optional[str] = Header(None)):
    token = _extract_bearer(authorization)
    if token and token in WRITE_TOKENS:
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid Authorization header")
