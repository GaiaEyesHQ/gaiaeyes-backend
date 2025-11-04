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


def _get_or_create_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        conninfo = _sanitize_conninfo(settings.DATABASE_URL)
        _pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=2,
            max_size=10,
            timeout=10,
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
    return pool


async def close_pool() -> None:
    global _pool_open
    async with _pool_lock:
        if _pool and _pool_open:
            await _pool.close()
            _pool_open = False


async def get_pool() -> AsyncConnectionPool:
    pool = await open_pool()
    return pool


async def get_db() -> AsyncGenerator:
    pool = await get_pool()
    attempt = 0
    last_exc: Optional[BaseException] = None

    while attempt < 2:
        ctx = pool.connection()
        try:
            conn = await ctx.__aenter__()
        except PoolTimeout as exc:
            last_exc = exc
            _log_pool_diag(pool)
            if attempt == 0:
                logger.warning("[DB] pool timeout; retrying after backoff")
                attempt += 1
                await asyncio.sleep(1.5)
                continue
            raise
        try:
            yield conn  # FastAPI injects this as `conn` in your endpoints
        except Exception as exc:  # pragma: no cover - defensive, FastAPI handles
            await ctx.__aexit__(type(exc), exc, exc.__traceback__)
            raise
        else:
            await ctx.__aexit__(None, None, None)
        return

    if last_exc:
        raise last_exc


def get_pool_metrics() -> Dict[str, Any]:
    pool = _get_or_create_pool()
    try:
        stats = pool.get_stats()
    except Exception:  # pragma: no cover - depends on psycopg internals
        stats = {}
    open_count = int(stats.get("pool_size", 0))
    free_count = int(stats.get("pool_available", 0))
    waiting = int(stats.get("requests_waiting", 0))
    last_refresh_iso = _pool_last_refresh.isoformat() if _pool_last_refresh else None
    return {
        "open": open_count,
        "free": free_count,
        "waiting": waiting,
        "last_refresh": last_refresh_iso,
    }
