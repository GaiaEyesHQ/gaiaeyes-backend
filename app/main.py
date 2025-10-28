from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime, timezone

from .routers import ingest, summary
 # Resilient imports for optional/relocated modules
try:
    # Preferred layout: app/api/...
    from .api.middleware import WebhookSigMiddleware  # type: ignore
except ModuleNotFoundError:
    try:
        from .middleware import WebhookSigMiddleware  # type: ignore
    except ModuleNotFoundError:
        WebhookSigMiddleware = None  # optional; skip if not present
try:
    from .api.webhooks import router as webhooks_router  # type: ignore
except ModuleNotFoundError:
    try:
        from .webhooks import router as webhooks_router  # type: ignore
    except ModuleNotFoundError:
        webhooks_router = None
from .utils.auth import require_auth as ensure_authenticated

def custom_generate_unique_id(route):
    # method + path is always unique
    return f"{list(route.methods)[0].lower()}_{route.path.replace('/', '_').strip('_')}"

app = FastAPI(
    title="Gaia Backend",
    version="0.1.0",
    generate_unique_id_function=custom_generate_unique_id
)

@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    # Always return a safe JSON envelope so the app can handle failures gracefully
    return JSONResponse(status_code=200, content={"ok": False, "data": None, "error": str(exc)})

@app.on_event("startup")
async def _log_routes():
    try:
        for r in app.routes:
            methods = list(getattr(r, "methods", []))
            path = getattr(r, "path", "")
            print(f"[ROUTE] {methods} {path}")
    except Exception:
        pass

# Build marker for health checks (update per deploy or wire to your CI SHA)
BUILD = "2025-09-20T02:45Z"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Verify HMAC signatures for all /hooks/* endpoints (if available)
if WebhookSigMiddleware is not None:
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
async def require_auth(request: Request):
    await ensure_authenticated(request)

# Mount routers WITH /v1 prefix and the auth dependency
app.include_router(ingest.router, prefix="/v1", dependencies=[Depends(require_auth)])
app.include_router(summary.router, dependencies=[Depends(require_auth)])

# Webhooks are protected by HMAC middleware, not bearer auth
if webhooks_router is not None:
    app.include_router(webhooks_router)
