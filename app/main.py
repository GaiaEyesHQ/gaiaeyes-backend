import logging
from datetime import datetime, timezone
from time import monotonic

from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout

from .routers import ingest, summary, symptoms
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
from .db import (
    get_pool,
    open_pool,
    close_pool,
    handle_connection_failure,
    handle_pool_timeout,
)


logger = logging.getLogger(__name__)

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


@app.on_event("shutdown")
async def _close_pool():
    await close_pool()

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


_DB_PROBE_TIMEOUT = 0.6
_DB_STICKY_GRACE_SECONDS = 30.0
_last_db_status: bool = True
_last_db_status_ts: float = monotonic()


async def _health_db_probe() -> tuple[bool, int, int]:
    global _last_db_status, _last_db_status_ts

    start = monotonic()
    probe_ok = False
    error_detail: str | None = None

    for attempt in range(2):
        try:
            pool = await get_pool()
            async with pool.connection(timeout=_DB_PROBE_TIMEOUT):
                probe_ok = True
                error_detail = None
                break
        except PoolTimeout:
            error_detail = "pool timeout"
            did_failover = await handle_pool_timeout("health probe pool timeout")
            if did_failover and attempt == 0:
                continue
            break
        except Exception as exc:  # pragma: no cover - defensive logging
            error_detail = str(exc)
            did_failover = await handle_connection_failure(exc)
            if did_failover and attempt == 0:
                continue
            break

    duration_ms = int((monotonic() - start) * 1000)
    now = monotonic()

    if probe_ok:
        _last_db_status = True
        _last_db_status_ts = now
        logger.info("[HEALTH] db probe ok latency=%dms", duration_ms)
        return True, 0, duration_ms

    age_seconds = now - _last_db_status_ts
    if age_seconds > _DB_STICKY_GRACE_SECONDS:
        _last_db_status = False
        _last_db_status_ts = now
        logger.warning(
            "[HEALTH] db probe failed after %dms: %s",
            duration_ms,
            error_detail or "unknown",
        )
        return False, 0, duration_ms

    sticky_age_ms = int(age_seconds * 1000)
    logger.warning(
        "[HEALTH] db probe failed after %dms (sticky %dms): %s",
        duration_ms,
        sticky_age_ms,
        error_detail or "unknown",
    )
    return _last_db_status, sticky_age_ms, duration_ms


@app.get("/health")
async def health():
    db_status, sticky_age_ms, latency_ms = await _health_db_probe()
    return {
        "ok": True,
        "service": "gaiaeyes-backend",
        "build": BUILD,
        "time": datetime.now(timezone.utc).isoformat(),
        "db": db_status,
        "db_sticky_age": sticky_age_ms,
        "db_latency_ms": latency_ms,
    }

# ---- Simple bearer auth for /v1/*
async def require_auth(request: Request):
    await ensure_authenticated(request)

# Mount routers WITH /v1 prefix and the auth dependency
app.include_router(ingest.router, prefix="/v1", dependencies=[Depends(require_auth)])
app.include_router(symptoms.router, prefix="/v1", dependencies=[Depends(require_auth)])
app.include_router(summary.router, dependencies=[Depends(require_auth)])

# Webhooks are protected by HMAC middleware, not bearer auth
if webhooks_router is not None:
    app.include_router(webhooks_router)
