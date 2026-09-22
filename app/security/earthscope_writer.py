"""Dedicated draft-worker credential; never a general read/write credential."""
import hashlib
import hmac
import os
import re

from fastapi import HTTPException, Request
from app.db import settings
from app.security.auth import READ_TOKENS, WRITE_TOKENS


def denied(code, status):
    raise HTTPException(status_code=status, detail={"code": code})


async def require_draft_worker(request: Request):
    if os.getenv("EARTHSCOPE_DRAFT_QUEUE_ENABLED", "0") != "1":
        denied("draft_queue_disabled", 503)
    worker_id = os.getenv("EARTHSCOPE_DRAFT_WORKER_ID", "")
    digest = os.getenv("EARTHSCOPE_DRAFT_WORKER_TOKEN_SHA256", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,79}", worker_id) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        denied("worker_unconfigured", 503)
    parts = request.headers.get("authorization", "").split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        denied("worker_auth_required", 401)
    token = parts[1]
    broad = READ_TOKENS | WRITE_TOKENS | {settings.DEV_BEARER, os.getenv("SUPABASE_SERVICE_ROLE_KEY"), os.getenv("SUPABASE_ANON_KEY")}
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token) or token in broad or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), digest):
        denied("worker_auth_required", 401)
    if request.headers.get("x-gaia-worker-id") != worker_id:
        denied("worker_identity_mismatch", 401)
    return worker_id
