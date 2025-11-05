# app/db.py
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, AsyncGenerator, Dict, Any
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from pydantic_settings import BaseSettings, SettingsConfigDict
from psycopg_pool import AsyncConnectionPool
from psycopg_pool.errors import PoolTimeout


logger = logging.getLogger(__name__)


_PGBOUNCER_PORT = 6543


class Settings(BaseSettings):
    DATABASE_URL: str
    DIRECT_URL: Optional[str] = None
    DEV_BEARER: Optional[str] = None
    CORS_ORIGINS: Optional[str] = "*"
    SUPABASE_JWT_SECRET: Optional[str] = None
    REDIS_URL: Optional[str] = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

_pool: AsyncConnectionPool | None = None
_pool_lock = asyncio.Lock()
_pool_open = False
_pool_last_refresh: Optional[datetime] = None
_pool_watchdog_task: Optional[asyncio.Task] = None
_pool_metrics_task: Optional[asyncio.Task] = None

_STATEMENT_TIMEOUT_MS = 60000


def _rebuild_netloc(u) -> str:
    username = u.username or ""
    password = u.password or ""
    host = u.hostname or ""

    if not host:
        return u.netloc or ""

    userinfo = ""
    if username:
        userinfo = username
        if password:
            userinfo += f":{password}"
        userinfo += "@"

    if host and ":" in host and not host.startswith("["):
        host = f"[{host}]"

    return f"{userinfo}{host}:{_PGBOUNCER_PORT}"


def _sanitize_conninfo(dsn: str) -> str:
    u = urlparse(dsn)
    qs = dict(parse_qsl(u.query, keep_blank_values=True))
    qs.pop("pgbouncer", None)
    qs.pop("prepare_threshold", None)
    qs.setdefault("sslmode", "require")
    new_q = urlencode(qs)
    netloc = u.netloc
    if (u.port or _PGBOUNCER_PORT) != _PGBOUNCER_PORT:
        logger.info("[DB] forcing pgBouncer port %s (was %s)", _PGBOUNCER_PORT, u.port)
        netloc = _rebuild_netloc(u)
    elif u.port is None:
        logger.info("[DB] applying pgBouncer default port %s", _PGBOUNCER_PORT)
        netloc = _rebuild_netloc(u)
    return urlunparse((u.scheme, netloc, u.path, u.params, new_q, u.fragment))


async def _check_on_acquire(conn) -> None:
    # Ensure a per-connection statement timeout and a quick ping
    await conn.execute(f"set statement_timeout = {_STATEMENT_TIMEOUT_MS}")
    async with conn.cursor() as cur:
        await cur.execute("select 1;")


def _log_pool_diag(pool: AsyncConnectionPool) -> None:
    try:
        stats = pool.get_stats()
    except Exception:  # pragma: no cover - depends on psycopg internals
        return
    open_count = int(stats.get("pool_size", 0))
    free_count = int(stats.get("pool_available", 0))
    waiting = int(stats.get("requests_waiting", 0))
    logger.info("[DB] diag: open=%s free=%s waiting=%s", open_count, free_count, waiting)


async def _pool_watchdog_loop(pool: AsyncConnectionPool) -> None:
    global _pool_last_refresh
    try:
        while True:
            await asyncio.sleep(60)
            if not _pool_open:
                continue
            try:
                async with pool.connection() as conn:
                    await conn.execute("select 1;")
                _pool_last_refresh = datetime.now(timezone.utc)
            except Exception as exc:  # pragma: no cover - depends on driver state
                logger.warning("[DB] watchdog ping failed: %s", exc)
    except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
        raise


async def _pool_metrics_loop(pool: AsyncConnectionPool) -> None:
    try:
        while True:
            await asyncio.sleep(60)
            if not _pool_open:
                continue
            metrics = get_pool_metrics()
            logger.info(
                "[DB] pool metrics open=%s used=%s waiting=%s",  # logged to stdout
                metrics.get("open"),
                metrics.get("used"),
                metrics.get("waiting"),
            )
    except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
        raise


def _start_pool_monitors(pool: AsyncConnectionPool) -> None:
    global _pool_watchdog_task, _pool_metrics_task
    loop = asyncio.get_running_loop()
    if _pool_watchdog_task is None or _pool_watchdog_task.done():
        _pool_watchdog_task = loop.create_task(_pool_watchdog_loop(pool))
    if _pool_metrics_task is None or _pool_metrics_task.done():
        _pool_metrics_task = loop.create_task(_pool_metrics_loop(pool))


async def _stop_pool_monitors() -> None:
    global _pool_watchdog_task, _pool_metrics_task
    for task in (_pool_watchdog_task, _pool_metrics_task):
        if task is not None:
            task.cancel()
    for task in (_pool_watchdog_task, _pool_metrics_task):
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:  # pragma: no cover - expected on cancel
                pass
    _pool_watchdog_task = None
    _pool_metrics_task = None


def _get_or_create_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        conninfo = _sanitize_conninfo(settings.DATABASE_URL)
        # NOTE: Supabase + pgBouncer (transaction mode) favors a small client pool.
        # Large client pools can cause churn and apparent flapping. Keep min small,
        # cap max to single digits, and use short acquire timeout to fail fast.
        _pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=2,
            max_size=8,
            timeout=8,
            max_idle=300,
            open=False,
            check=_check_on_acquire,
            kwargs={
                "sslmode": "require",
            },
        )
        logger.info(
            "[DB] async pool configured for pgBouncer transaction mode on port %s", _PGBOUNCER_PORT
        )
    return _pool


async def open_pool() -> AsyncConnectionPool:
    global _pool_open, _pool_last_refresh
    async with _pool_lock:
        pool = _get_or_create_pool()
        if not _pool_open:
            await pool.open()
            _pool_last_refresh = datetime.now(timezone.utc)
            _pool_open = True
            _log_pool_diag(pool)
            _start_pool_monitors(pool)
    return pool


async def close_pool() -> None:
    global _pool_open
    async with _pool_lock:
        if _pool and _pool_open:
            await _stop_pool_monitors()
            await _pool.close()
            _pool_open = False


async def get_pool() -> AsyncConnectionPool:
    pool = await open_pool()
    return pool


async def get_db() -> AsyncGenerator:
    pool = await get_pool()
    attempts = 0
    ctx = None
    while attempts < 2:
        attempts += 1
        ctx = pool.connection()
        try:
            conn = await ctx.__aenter__()
        except PoolTimeout:
            _log_pool_diag(pool)
            if attempts < 2:
                backoff = 1.5
                logger.warning("[DB] pool timeout; retrying after %.1fs", backoff)
                await asyncio.sleep(backoff)
                continue
            raise

        try:
            await conn.execute(f"set statement_timeout = {_STATEMENT_TIMEOUT_MS}")
        except Exception as exc:
            await ctx.__aexit__(type(exc), exc, exc.__traceback__)
            raise

        try:
            yield conn  # FastAPI injects this as `conn` in your endpoints
        except Exception as exc:  # pragma: no cover - defensive, FastAPI handles
            await ctx.__aexit__(type(exc), exc, exc.__traceback__)
            raise
        else:
            await ctx.__aexit__(None, None, None)
        return

    raise RuntimeError("DB connection acquisition failed")


def get_pool_metrics() -> Dict[str, Any]:
    pool = _get_or_create_pool()
    try:
        stats = pool.get_stats()
    except Exception:  # pragma: no cover - depends on psycopg internals
        stats = {}
    open_count = int(stats.get("pool_size", 0))
    free_count = int(stats.get("pool_available", 0))
    waiting = int(stats.get("requests_waiting", 0))
    used = max(open_count - free_count, 0)
    last_refresh_iso = _pool_last_refresh.isoformat() if _pool_last_refresh else None
    db_ok = bool(_pool_open)
    return {
        "open": open_count,
        "free": free_count,
        "used": used,
        "waiting": waiting,
        "last_refresh": last_refresh_iso,
        "ok": db_ok,
    }
