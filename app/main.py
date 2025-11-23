import logging

from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routers import health as health_router, ingest, summary, symptoms, space_visuals

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
from .db import get_pool, open_pool, close_pool
from .db.health import ensure_health_monitor_started, stop_health_monitor
from .routers.space_visuals import _media_base


logger = logging.getLogger(__name__)

def custom_generate_unique_id(route):
    # method + path is always unique
    return f"{list(route.methods)[0].lower()}_{route.path.replace('/', '_').strip('_')}"

app = FastAPI(
    title="Gaia Backend",
    version="0.1.0",
    generate_unique_id_function=custom_generate_unique_id
)

logging.getLogger("uvicorn").info(f"[visuals] media_base at startup: {_media_base() or 'None'}")

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


@app.on_event("startup")
async def _open_pool():
    await open_pool()


@app.on_event("startup")
async def _check_db_ready():
    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("select 1;")
                await cur.fetchone()
        logger.info("[DB] ready")
    except Exception as exc:  # pragma: no cover - startup diagnostics
        logger.exception("[DB] startup check failed: %s", exc)


@app.on_event("startup")
async def _start_health_monitor():
    await ensure_health_monitor_started()


@app.on_event("shutdown")
async def _stop_health_monitor():
    await stop_health_monitor()


@app.on_event("shutdown")
async def _close_pool():
    await close_pool()

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


# ---- Simple bearer auth for /v1/*
async def require_auth(request: Request):
    await ensure_authenticated(request)

# Public health endpoint
app.include_router(health_router.router)

# Mount routers WITH /v1 prefix and the auth dependency
app.include_router(ingest.router, prefix="/v1", dependencies=[Depends(require_auth)])
app.include_router(symptoms.router, prefix="/v1", dependencies=[Depends(require_auth)])
app.include_router(summary.router, dependencies=[Depends(require_auth)])
app.include_router(space_visuals.router)

# Webhooks are protected by HMAC middleware, not bearer auth
if webhooks_router is not None:
    app.include_router(webhooks_router)
