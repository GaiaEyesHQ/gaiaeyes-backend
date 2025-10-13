from fastapi import FastAPI, Depends, Header, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone

from uuid import UUID

from .db import settings
from .routers import ingest, summary
from .api.middleware import WebhookSigMiddleware
from .api.webhooks import router as webhooks_router

def custom_generate_unique_id(route):
    # method + path is always unique
    return f"{list(route.methods)[0].lower()}_{route.path.replace('/', '_').strip('_')}"

app = FastAPI(
    title="Gaia Backend",
    version="0.1.0",
    generate_unique_id_function=custom_generate_unique_id
)

# Build marker for health checks (update per deploy or wire to your CI SHA)
BUILD = "2025-09-20T02:45Z"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Verify HMAC signatures for all /hooks/* endpoints
app.add_middleware(WebhookSigMiddleware)


@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": "gaiaeyes-backend",
        "build": BUILD,
        "time": datetime.now(timezone.utc).isoformat()
    }

# ---- Simple bearer auth for /v1/*
async def require_auth(
    request: Request,
    authorization: str = Header(..., alias="Authorization"),
    x_dev_userid: str | None = Header(None, alias="X-Dev-UserId"),
):
    # Bearer token check
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    if not settings.DEV_BEARER or token != settings.DEV_BEARER:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid bearer token")

    # Optional: propagate user_id into request.state if provided and looks like a UUID
    request.state.user_id = None
    if x_dev_userid:
        try:
            _ = UUID(x_dev_userid)
            request.state.user_id = x_dev_userid
        except Exception:
            # leave as None if invalid
            pass

# Mount routers WITH /v1 prefix and the auth dependency
app.include_router(ingest.router, prefix="/v1", dependencies=[Depends(require_auth)])
app.include_router(summary.router, dependencies=[Depends(require_auth)])

# Webhooks are protected by HMAC middleware, not bearer auth
app.include_router(webhooks_router)
